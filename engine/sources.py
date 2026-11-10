"""Pulls raw postings from Adzuna + Greenhouse/Lever/Ashby + jobspy
(Indeed/Glassdoor/ZipRecruiter), normalizes them to a common dict shape,
then filters per config.yaml.

Every posting carries its own match_reason string so the run summary
(and the Notion row) shows exactly why it passed.

Note on jobspy: it scrapes rather than using an official API, so it's
more fragile than Adzuna/Greenhouse/Lever/Ashby (site markup changes can
break it, and heavy use can get you rate-limited). LinkedIn is
deliberately excluded from the site list here — same ToS/fragility
reasoning that keeps it out of automation elsewhere in this pipeline.
If jobspy errors out, the run continues with whatever other sources
returned; it never blocks the rest of the pipeline.
"""
import html as _html
import os
import re
from datetime import datetime, timedelta, timezone

import requests

UA = {"User-Agent": "job-search-script/1.0"}

DESCRIPTION_MAX_CHARS = 1200  # keeps the draft prompt a reasonable size


def _html_to_text(raw: str) -> str:
    """Full-length plain text from HTML. Unescapes first because
    Greenhouse returns its content HTML-escaped (&lt;p&gt;...), which a
    plain tag regex wouldn't catch."""
    if not raw:
        return ""
    text = _html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_html(raw: str) -> str:
    """Minimal tag stripper — good enough for feeding a description into
    a prompt; not meant to preserve formatting."""
    return _html_to_text(raw)[:DESCRIPTION_MAX_CHARS]


# ── Salary extraction from free text ────────────────────────────
# Company boards (Greenhouse/Lever/Ashby) don't return salary as a field,
# but most postings include a pay range in the description (CA pay
# transparency law). It's usually at the END of the posting, so this
# must run on the full text, not the truncated description.

_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kKmMbB])?"
_RANGE_RE = re.compile(
    r"\$\s?" + _NUM +
    r"\s*(?:USD|usd)?\s*(?:-|–|—|to)\s*(?:USD\s*|[A-Z]{1,2}(?=\$))?\$?\s?" + _NUM
)
# Text right after a range that means it isn't an annual base salary.
_NON_ANNUAL_RE = re.compile(
    r"^\W{0,3}\s*(?:usd\s*)?(?:/|per|an|a)?\s*(?:hour|hr\b|month|mo\b|week|day)"
    r"|^\W{0,3}\s*(?:usd\s*)?(?:in\s+)?equity",
    re.IGNORECASE,
)
ANNUAL_MIN, ANNUAL_MAX = 40_000, 2_000_000
# Non-USD ranges ("CAD $138,600", "CA$138.6K", "$161,600 — $222,200 CAD")
# would be wrongly compared against a USD minimum, so they're skipped.
_FOREIGN_BEFORE_RE = re.compile(
    r"(?:\b(?:CAD|AUD|NZD|SGD|HKD|MXN|EUR|GBP)\s*|(?<![A-Za-z])(?:CA|C|A|AU|NZ|S|HK|MX))$")
_FOREIGN_AFTER_RE = re.compile(r"^\s*(?:CAD|AUD|NZD|SGD|HKD|MXN|EUR|GBP)\b")


def _to_amount(num: str, suffix: str):
    if suffix and suffix.lower() in ("m", "b"):
        return None  # "$5M–$10M" is funding/revenue, not pay
    val = float(num.replace(",", ""))
    if suffix and suffix.lower() == "k":
        val *= 1000
    return int(val)


def extract_salary(text: str) -> str:
    """Finds annual salary ranges like "$185,000 — $240,000 USD" or
    "$204K – $264K" in free text. Ignores hourly/monthly ranges, equity,
    and funding amounts. If several ranges are listed (pay zones), returns
    the highest one (usually the highest-cost-of-living zone). Returns ""
    when nothing trustworthy is found, so the job stays "verify salary"
    rather than being wrongly dropped."""
    if not text:
        return ""
    best = None
    for m in _RANGE_RE.finditer(text):
        # "$185 – $240K": the K on the upper number applies to both.
        lo = _to_amount(m.group(1), m.group(2) or m.group(4))
        hi = _to_amount(m.group(3), m.group(4) or m.group(2))
        if lo is None or hi is None:
            continue
        if _NON_ANNUAL_RE.search(text[m.end():m.end() + 25]):
            continue
        if (_FOREIGN_BEFORE_RE.search(text[max(0, m.start() - 6):m.start()])
                or _FOREIGN_AFTER_RE.search(text[m.end():m.end() + 8])):
            continue
        if not (ANNUAL_MIN <= lo <= hi <= ANNUAL_MAX):
            continue
        if best is None or hi > best[1]:
            best = (lo, hi)
    if not best:
        return ""
    return f"${best[0]:,}–${best[1]:,}"


# ── Fetchers ─────────────────────────────────────────────────────

def fetch_adzuna(config) -> list[dict]:
    cfg = config.get("adzuna") or {}
    app_id = os.environ.get(cfg.get("app_id_env", "ADZUNA_APP_ID"), "").strip()
    app_key = os.environ.get(cfg.get("app_key_env", "ADZUNA_APP_KEY"), "").strip()
    if not app_id or not app_key:
        print("  [adzuna] skipped (optional add-on, not set up)")
        return []

    url = f"https://api.adzuna.com/v1/api/jobs/{cfg.get('country', 'us')}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": cfg.get("what") or "product designer",
        "where": cfg.get("where") or config.get("search_location") or "",
        "results_per_page": 50,
        "max_days_old": config.get("max_posting_age_days", 30),
        "content-type": "application/json",
    }
    resp = requests.get(url, params=params, headers=UA, timeout=30)
    resp.raise_for_status()
    raw = resp.json().get("results", [])

    jobs = []
    for r in raw:
        jobs.append({
            "title": r.get("title", ""),
            "company": (r.get("company") or {}).get("display_name", "Unknown"),
            "location": (r.get("location") or {}).get("display_name", ""),
            "url": r.get("redirect_url", ""),
            "salary": _adzuna_salary(r),
            "posted_date": (r.get("created") or "")[:10],
            "source": "Adzuna",
            "description": _strip_html(r.get("description", "")),
            # Adzuna's redirect_url includes a session-specific tracking
            # token that changes on every API call, even for the same
            # posting — using it for dedup would write duplicates every
            # run. Adzuna's own numeric "id" is stable across calls.
            "job_key": f"adzuna:{r.get('id', '')}",
        })
    print(f"  [adzuna] fetched {len(jobs)}")
    return jobs


def _adzuna_salary(r) -> str:
    lo, hi = r.get("salary_min"), r.get("salary_max")
    if lo or hi:
        return f"${int(lo or hi):,}–${int(hi or lo):,}"
    return ""


def fetch_greenhouse(config) -> list[dict]:
    jobs = []
    for company in config.get("greenhouse_companies", []):
        try:
            # content=true includes the full job description in the list
            # response, so we don't need a second request per posting.
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
            resp = requests.get(url, headers=UA, timeout=20)
            resp.raise_for_status()
            for r in resp.json().get("jobs", []):
                full_text = _html_to_text(r.get("content", ""))
                jobs.append({
                    "title": r.get("title", ""),
                    "company": company,
                    "location": (r.get("location") or {}).get("name", ""),
                    "url": r.get("absolute_url", ""),
                    "salary": _safe_salary(full_text),
                    "posted_date": (r.get("updated_at") or "")[:10],
                    "source": "Greenhouse",
                    "description": full_text[:DESCRIPTION_MAX_CHARS],
                    "job_key": f"greenhouse:{company}:{r.get('id', '')}",
                })
        except requests.RequestException as e:
            print(f"  [greenhouse:{company}] error — {e}")
    print(f"  [greenhouse] fetched {len(jobs)}")
    return jobs


def fetch_lever(config) -> list[dict]:
    jobs = []
    for company in config.get("lever_companies", []):
        try:
            url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            resp = requests.get(url, headers=UA, timeout=20)
            resp.raise_for_status()
            for r in resp.json():
                jobs.append({
                    "title": r.get("text", ""),
                    "company": company,
                    "location": (r.get("categories") or {}).get("location", ""),
                    "url": r.get("hostedUrl", ""),
                    "salary": _lever_salary(r),
                    "posted_date": _lever_date(r.get("createdAt")),
                    "source": "Lever",
                    "description": _strip_html(r.get("descriptionPlain") or r.get("description", "")),
                    "job_key": f"lever:{company}:{r.get('id', '')}",
                })
        except requests.RequestException as e:
            print(f"  [lever:{company}] error — {e}")
    print(f"  [lever] fetched {len(jobs)}")
    return jobs


def _lever_salary(r) -> str:
    """Lever's structured salaryRange when it's annual, else a range
    found anywhere in the posting text (description, lists, closing)."""
    try:
        sr = r.get("salaryRange") or {}
        interval = str(sr.get("interval") or "").lower()
        if sr.get("min") and ("year" in interval or "annual" in interval):
            lo, hi = int(sr["min"]), int(sr.get("max") or sr["min"])
            if ANNUAL_MIN <= lo <= hi <= ANNUAL_MAX:
                return f"${lo:,}–${hi:,}"
    except (TypeError, ValueError):
        pass
    parts = [r.get("descriptionPlain") or _html_to_text(r.get("description", "")),
             r.get("additionalPlain") or _html_to_text(r.get("additional", ""))]
    for lst in r.get("lists") or []:
        if isinstance(lst, dict):
            parts.append(_html_to_text(lst.get("content", "")))
    return _safe_salary(" ".join(p for p in parts if p))


def _safe_salary(text: str) -> str:
    """extract_salary that can never break a run — worst case, the job
    just stays "salary unlisted — verify", same as before this existed."""
    try:
        return extract_salary(text)
    except Exception:
        return ""


def _lever_date(ms) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def fetch_ashby(config) -> list[dict]:
    jobs = []
    for company in config.get("ashby_companies", []):
        try:
            # includeCompensation=true adds a structured pay summary
            # ("$204K – $264K • Offers Equity") when the company sets one.
            url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
            resp = requests.get(url, headers=UA, timeout=20)
            resp.raise_for_status()
            for r in resp.json().get("jobs", []):
                full_text = _html_to_text(r.get("descriptionHtml") or r.get("descriptionPlain", ""))
                jobs.append({
                    "title": r.get("title", ""),
                    "company": company,
                    "location": r.get("location", ""),
                    "url": r.get("jobUrl", ""),
                    "salary": _ashby_salary(r, full_text),
                    "posted_date": (r.get("publishedAt") or "")[:10],
                    "source": "Ashby",
                    "description": full_text[:DESCRIPTION_MAX_CHARS],
                    "job_key": f"ashby:{company}:{r.get('id', '')}",
                })
        except requests.RequestException as e:
            print(f"  [ashby:{company}] error — {e}")
    print(f"  [ashby] fetched {len(jobs)}")
    return jobs


def _ashby_salary(r, full_text: str) -> str:
    comp = r.get("compensation") or {}
    if isinstance(comp, dict):
        for key in ("scrapeableCompensationSalarySummary", "compensationTierSummary"):
            found = _safe_salary(str(comp.get(key) or ""))
            if found:
                return found
    return _safe_salary(full_text)


def fetch_jobspy(config) -> list[dict]:
    """Indeed, Glassdoor, ZipRecruiter via jobspy. LinkedIn intentionally
    excluded — direct scraping there violates ToS and breaks often; use
    the manual saved-search habit from the README instead."""
    cfg = config.get("jobspy")
    if not cfg:
        return []
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("  [jobspy] skipped (not installed; paste the install line from the README again)")
        return []

    try:
        df = scrape_jobs(
            site_name=cfg.get("sites", ["indeed"]),
            search_term=cfg.get("search_term", "product designer"),
            location=cfg.get("location") or config.get("search_location") or "United States",
            results_wanted=cfg.get("results_wanted", 40),
            hours_old=config.get("max_posting_age_days", 30) * 24,
            is_remote=False,  # location string above already covers "remote"
            country_indeed="USA",
        )
    except Exception as e:
        print(f"  [jobspy] error — {e}")
        return []

    jobs = []
    for _, r in df.iterrows():
        raw_desc = r.get("description")
        job_url = str(r.get("job_url") or "")
        raw_id = r.get("id")
        jobs.append({
            "title": str(r.get("title") or ""),
            "company": str(r.get("company") or "Unknown"),
            "location": str(r.get("location") or ""),
            "url": job_url,
            "salary": _jobspy_salary(r) or (
                _safe_salary(_html_to_text(raw_desc)) if isinstance(raw_desc, str) else ""),
            "posted_date": _jobspy_date(r.get("date_posted")),
            "source": f"jobspy:{r.get('site', 'unknown')}",
            "description": _strip_html(raw_desc) if isinstance(raw_desc, str) else "",
            # jobspy provides a stable per-posting id on most sites; fall
            # back to the URL (stripped of query string, which is where
            # tracking params tend to live) if it's missing.
            "job_key": f"jobspy:{raw_id}" if raw_id and str(raw_id) != "nan"
                       else f"jobspy:{job_url.split('?')[0]}",
        })
    print(f"  [jobspy] fetched {len(jobs)}")
    return jobs


# jobspy reports pay per its "interval" column; the filter compares
# against an annual minimum, so convert (an $85/hr role was previously
# read as "$85" and wrongly dropped as below the salary floor).
_ANNUALIZE = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 260, "hourly": 2080}


def _jobspy_salary(r) -> str:
    def num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f and f > 0 else None  # drops NaN / zero

    lo, hi = num(r.get("min_amount")), num(r.get("max_amount"))
    if lo is None and hi is None:
        return ""
    lo, hi = lo or hi, hi or lo
    interval = str(r.get("interval") or "").lower()
    mult = _ANNUALIZE.get(interval)
    if mult is None:
        # Unknown/missing interval: only trust it if it already looks annual.
        mult = 1 if lo >= ANNUAL_MIN else None
    if mult is None:
        return ""
    return f"${int(lo * mult):,}–${int(hi * mult):,}"


def _jobspy_date(val) -> str:
    if val is None or (isinstance(val, float) and val != val):  # NaN check
        return ""
    return str(val)[:10]


# ── Filtering ────────────────────────────────────────────────────

def filter_jobs(jobs: list[dict], config: dict) -> tuple[list[dict], dict]:
    """Returns (matches, stats). Every dropped job increments a reason
    counter so the run summary explains where postings went."""
    stats = {"scanned": len(jobs), "no_title_match": 0, "no_seniority": 0,
              "excluded_title": 0, "bad_location": 0, "too_old": 0,
              "salary_too_low": 0}
    matches = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.get("max_posting_age_days", 30))

    unleveled_min = config.get("unleveled_min_salary")

    for job in jobs:
        title_l = job["title"].lower()

        if not _has_any(title_l, config.get("title_keywords") or []):
            stats["no_title_match"] += 1
            continue
        if _has_any(title_l, config.get("title_excludes") or [], whole_word=True):
            stats["excluded_title"] += 1
            continue
        # Some companies post senior roles as plain "Product Designer".
        # If the top of the listed range is at least unleveled_min_salary,
        # treat the pay as the seniority signal. An empty
        # seniority_keywords list turns the level check off entirely.
        unleveled_pay = None
        seniority = config.get("seniority_keywords") or []
        if seniority and not _has_any(title_l, seniority):
            ceiling = _parse_salary_ceiling(job.get("salary", ""))
            if unleveled_min and ceiling is not None and ceiling >= unleveled_min:
                unleveled_pay = ceiling
            else:
                stats["no_seniority"] += 1
                continue

        if not _location_ok(job["location"].lower(), config):
            stats["bad_location"] += 1
            continue

        if job.get("posted_date"):
            try:
                posted = datetime.strptime(job["posted_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if posted < cutoff:
                    stats["too_old"] += 1
                    continue
            except ValueError:
                pass  # unparseable date — don't drop on a formatting fluke

        is_contract = any(c in title_l for c in config.get("contract_keywords", []))
        # Compare the TOP of the range: a role is only dropped if even its
        # maximum is below min_salary. Bottom-of-range ends are usually
        # lower levels / lower-cost zones, and dropping on them hid roles
        # like a $166k–$229k Staff Designer.
        salary_num = _parse_salary_ceiling(job.get("salary", ""))
        if not is_contract and salary_num is not None and salary_num < (config.get("min_salary") or 0):
            stats["salary_too_low"] += 1
            continue

        job["match_reason"] = _match_reason(job, config, salary_num, is_contract)
        if unleveled_pay is not None:
            job["match_reason"] += (
                f"; no level in title, but pay reaches ${unleveled_min:,}+ "
                "— confirm seniority before applying")
        matches.append(job)

    return matches, stats


def _has_any(text: str, keywords, whole_word: bool = False) -> bool:
    """Keyword match that only starts at a word boundary, so "ux" doesn't
    match "luxury" but "product design" still matches "product designer".
    whole_word=True also requires a boundary at the end ("intern" won't
    exclude "Internal Tools")."""
    for k in keywords:
        pattern = r"(?<![a-z0-9])" + re.escape(k.lower())
        if whole_word and k[-1].isalnum():
            pattern += r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


_US_RE = re.compile(r"(?<![a-z])(?:us|u\.s\.?|usa|united states)(?![a-z])")


def _location_ok(loc_l: str, config: dict) -> bool:
    """A named place from your locations list always qualifies. "Remote" qualifies unless
    the listing is remote somewhere outside the US ("Remote - Canada",
    "Remote UK") and doesn't also mention the US. Remote jobs only count
    if "remote" is in your locations list. An empty list means anywhere."""
    locations = [l.lower() for l in config.get("locations") or []]
    if not locations:
        return True
    remote_words = {"remote"}
    places = [l for l in locations if l not in remote_words]
    if _has_any(loc_l, places):
        return True
    if "remote" not in locations or not _has_any(loc_l, remote_words):
        return False
    non_us = config.get("remote_excludes", [])
    if _has_any(loc_l, non_us, whole_word=True) and not _US_RE.search(loc_l):
        return False
    return True


def _parse_salary_floor(salary_str: str):
    nums = re.findall(r"[\d,]+", salary_str or "")
    if not nums:
        return None
    return int(nums[0].replace(",", ""))


def _parse_salary_ceiling(salary_str: str):
    nums = re.findall(r"\d[\d,]*", salary_str or "")
    if not nums:
        return None
    return int(nums[-1].replace(",", ""))


def _match_reason(job, config, salary_num, is_contract=False) -> str:
    parts = [
        f"title matches '{job['title']}'",
        f"location '{job['location']}' qualifies",
        f"posted {job.get('posted_date') or 'unknown'} (within {config.get('max_posting_age_days', 30)}d)",
    ]
    if is_contract:
        parts.append(
            f"fractional/contract role — salary minimum waived"
            + (f" (listed: {job['salary']})" if salary_num else " (unlisted)")
        )
    else:
        parts.append(
            f"salary {job['salary']} reaches ≥ ${config.get('min_salary') or 0:,}" if salary_num
            else "salary unlisted — verify before applying"
        )
    return "; ".join(parts)
