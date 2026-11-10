"""Tests for filter_jobs — the part that decides what's "correct."
Run from the project folder: venv/bin/python -m pytest -q
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from sources import (filter_jobs, _parse_salary_floor, _parse_salary_ceiling, fetch_adzuna, fetch_greenhouse,
                     fetch_ashby, extract_salary, _html_to_text, _lever_salary,
                     _jobspy_salary, _safe_salary)

CONFIG = {
    "title_keywords": ["product design", "ux"],
    "seniority_keywords": ["senior", "staff", "principal", "lead"],
    "title_excludes": ["junior", "jr.", "intern", "associate", "ux engineer", "design engineer",
                        "software engineer", "frontend engineer", "front-end engineer", "researcher"],
    "locations": ["chicago", "evanston", "remote"],
    "min_salary": 190000,  # test value
    "max_posting_age_days": 30,
    "contract_keywords": ["fractional", "contract", "contractor", "freelance", "consultant", "consulting", "interim"],
}


def _job(**overrides):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = {
        "title": "Senior Product Designer",
        "company": "TestCo",
        "location": "Chicago, IL",
        "url": "https://example.com/job/1",
        "salary": "$200,000–$240,000",
        "posted_date": today,
        "source": "Test",
    }
    base.update(overrides)
    return base


def test_clean_match_passes():
    matches, stats = filter_jobs([_job()], CONFIG)
    assert len(matches) == 1
    assert stats["scanned"] == 1


def test_title_without_keyword_dropped():
    matches, stats = filter_jobs([_job(title="Senior Backend Engineer")], CONFIG)
    assert len(matches) == 0
    assert stats["no_title_match"] == 1


def test_junior_excluded_even_with_ux_in_title():
    matches, stats = filter_jobs([_job(title="Junior UX Designer")], CONFIG)
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_missing_seniority_dropped():
    matches, stats = filter_jobs([_job(title="Product Designer")], CONFIG)
    assert len(matches) == 0
    assert stats["no_seniority"] == 1


def test_wrong_location_dropped():
    matches, stats = filter_jobs([_job(location="Austin, TX")], CONFIG)
    assert len(matches) == 0
    assert stats["bad_location"] == 1


def test_remote_location_passes():
    matches, _ = filter_jobs([_job(location="Remote (US)")], CONFIG)
    assert len(matches) == 1


def test_stale_posting_dropped():
    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    matches, stats = filter_jobs([_job(posted_date=old_date)], CONFIG)
    assert len(matches) == 0
    assert stats["too_old"] == 1


def test_salary_below_minimum_dropped():
    matches, stats = filter_jobs([_job(salary="$150,000–$170,000")], CONFIG)
    assert len(matches) == 0
    assert stats["salary_too_low"] == 1


def test_unlisted_salary_passes_flagged():
    matches, _ = filter_jobs([_job(salary="")], CONFIG)
    assert len(matches) == 1
    assert "verify" in matches[0]["match_reason"]


def test_unparseable_date_not_dropped():
    matches, _ = filter_jobs([_job(posted_date="not-a-date")], CONFIG)
    assert len(matches) == 1  # shouldn't silently drop on a format fluke


def test_salary_parsing():
    assert _parse_salary_floor("$200,000–$240,000") == 200000
    assert _parse_salary_floor("") is None
    assert _parse_salary_floor("Competitive") is None
    assert _parse_salary_floor("190000") == 190000


def test_fractional_role_bypasses_salary_floor():
    matches, stats = filter_jobs(
        [_job(title="Fractional Senior Product Designer", salary="$8,000/month")], CONFIG
    )
    assert len(matches) == 1
    assert stats["salary_too_low"] == 0
    assert "salary minimum waived" in matches[0]["match_reason"]


def test_contract_role_with_no_salary_still_passes():
    matches, _ = filter_jobs(
        [_job(title="Senior UX Contractor", salary="")], CONFIG
    )
    assert len(matches) == 1
    assert "waived" in matches[0]["match_reason"]


def test_non_contract_role_still_enforces_salary_floor():
    matches, stats = filter_jobs(
        [_job(title="Senior Product Designer", salary="$120,000")], CONFIG
    )
    assert len(matches) == 0
    assert stats["salary_too_low"] == 1


def test_consulting_keyword_also_waives_salary():
    matches, _ = filter_jobs(
        [_job(title="Senior UX Consulting Lead", salary="$50,000")], CONFIG
    )
    assert len(matches) == 1


def test_ux_engineer_excluded():
    matches, stats = filter_jobs(
        [_job(title="Senior Staff UX Engineer, Cloud AI")], CONFIG
    )
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_design_engineer_excluded():
    matches, stats = filter_jobs(
        [_job(title="Senior Product Design Engineer")], CONFIG
    )
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_plain_ux_designer_still_passes():
    matches, _ = filter_jobs(
        [_job(title="Senior UX Designer, Search App")], CONFIG
    )
    assert len(matches) == 1


def test_software_engineer_with_ux_in_title_excluded():
    matches, stats = filter_jobs(
        [_job(title="Senior Software Engineer, Mobile (Repayment UX)")], CONFIG
    )
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_frontend_engineer_with_ux_excluded():
    matches, stats = filter_jobs(
        [_job(title="Principal Frontend Software Engineer - Discovery UX")], CONFIG
    )
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_ux_researcher_excluded():
    matches, stats = filter_jobs(
        [_job(title="Senior UX Researcher, Consumer Product")], CONFIG
    )
    assert len(matches) == 0
    assert stats["excluded_title"] == 1


def test_adzuna_job_key_is_stable_despite_shifting_redirect_url():
    """Regression test for the Notion-duplicate bug: Adzuna issues a
    different tracking URL for the same posting on every API call, so
    dedup must key on Adzuna's own numeric id, not the URL."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "results": [
            {
                "id": "5829998456",
                "title": "Senior Product Designer",
                "company": {"display_name": "TestCo"},
                "location": {"display_name": "Chicago, IL"},
                "redirect_url": "https://www.adzuna.com/details/5829998456?se=AAA&v=111",
                "created": "2026-08-05",
                "description": "",
            },
            {
                "id": "5829998456",  # same job, different call
                "title": "Senior Product Designer",
                "company": {"display_name": "TestCo"},
                "location": {"display_name": "Chicago, IL"},
                "redirect_url": "https://www.adzuna.com/land/ad/5829998456?se=BBB&v=222",
                "created": "2026-08-05",
                "description": "",
            },
        ]
    }
    fake_response.raise_for_status = lambda: None

    with patch("sources.requests.get", return_value=fake_response):
        with patch.dict("os.environ", {"ADZUNA_APP_ID": "x", "ADZUNA_APP_KEY": "y"}):
            jobs = fetch_adzuna({
                "adzuna": {
                    "app_id_env": "ADZUNA_APP_ID",
                    "app_key_env": "ADZUNA_APP_KEY",
                    "country": "us", "what": "ux", "where": "SF",
                },
                "max_posting_age_days": 30,
            })

    assert len(jobs) == 2
    assert jobs[0]["url"] != jobs[1]["url"]  # URLs genuinely differ, as in the real bug
    assert jobs[0]["job_key"] == jobs[1]["job_key"] == "adzuna:5829998456"


# ── Salary extraction from description text ─────────────────────
# Formats below are copied from real postings (various
# Greenhouse and Ashby companies).

def test_range_reaching_minimum_is_kept():
    """Salary rule compares the TOP of the range to min_salary."""
    matches, stats = filter_jobs([_job(salary="$166,600–$229,150")], CONFIG)
    assert len(matches) == 1 and stats["salary_too_low"] == 0


def test_range_entirely_below_minimum_dropped():
    matches, stats = filter_jobs([_job(salary="$140,000–$185,000")], CONFIG)
    assert len(matches) == 0 and stats["salary_too_low"] == 1


def test_salary_ceiling_parsing():
    assert _parse_salary_ceiling("$200,000–$240,000") == 240000
    assert _parse_salary_ceiling("$120,000") == 120000
    assert _parse_salary_ceiling("") is None
    assert _parse_salary_ceiling("Competitive") is None


def test_extract_greenhouse_style_range():
    t = "...applicable law. Annual Base Salary Range: $153,000 — $221,000 USD At Acme we..."
    assert extract_salary(t) == "$153,000–$221,000"


def test_extract_k_style_range():
    assert extract_salary("$204K – $264K • Offers Equity") == "$204,000–$264,000"
    assert extract_salary("$185 - $240k") == "$185,000–$240,000"


def test_extract_picks_highest_pay_zone():
    t = ("US Zone 1 $164,800 — $223,000 USD US Zone 2 $146,500 — $198,300 USD "
         "US Zone 3 $130,200 — $176,200 USD")
    assert extract_salary(t) == "$164,800–$223,000"


def test_extract_ignores_hourly():
    assert extract_salary("Hourly Rate: $60 — $60 USD Application Limit") == ""
    assert extract_salary("Pay: $75 - $95 per hour") == ""
    assert extract_salary("$90,000 - $120,000 per month") == ""


def test_extract_ignores_funding_and_equity():
    assert extract_salary("We raised $50M - $100M from top investors") == ""
    assert extract_salary("$100,000 - $200,000 in equity") == ""


def test_extract_skips_non_usd_ranges():
    assert extract_salary("Annual Base Salary $161,600 — $222,200 CAD Total Rewards") == ""
    assert extract_salary("Compensation Range CAD $138,600 - $207,800 Depending") == ""
    assert extract_salary("CA$138.6K – CA$207.8K • Offers Equity") == ""
    # USD labels must still work
    assert extract_salary("USD $150,000 - $180,000") == "$150,000–$180,000"
    assert extract_salary("US$150,000 - US$180,000") == "$150,000–$180,000"
    assert extract_salary("Base: $150,000 - $180,000 USD") == "$150,000–$180,000"


def test_extract_nothing_found():
    assert extract_salary("") == ""
    assert extract_salary(None) == ""
    assert extract_salary("Competitive salary and great benefits") == ""


def test_html_to_text_handles_escaped_greenhouse_html():
    raw = "&lt;p&gt;Annual Base Salary Range: $180,370 &amp;mdash; $212,200 USD&lt;/p&gt;"
    text = _html_to_text(raw)
    assert "<p>" not in text and "&lt;" not in text
    assert extract_salary(text) == "$180,370–$212,200"


def _fake_get(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = lambda: None
    return resp


def test_greenhouse_salary_found_past_truncation_point():
    """Pay ranges sit at the end of postings — must be found even though
    the stored description is cut to DESCRIPTION_MAX_CHARS."""
    content = "&lt;p&gt;" + ("Lorem ipsum. " * 300) + \
              "Annual Base Salary Range: $150,000 — $180,000 USD&lt;/p&gt;"
    payload = {"jobs": [{"id": 1, "title": "Senior Product Designer",
                         "location": {"name": "Chicago, IL"},
                         "absolute_url": "https://x", "updated_at": "2026-11-01",
                         "content": content}]}
    with patch("sources.requests.get", return_value=_fake_get(payload)):
        jobs = fetch_greenhouse({"greenhouse_companies": ["testco"]})
    assert jobs[0]["salary"] == "$150,000–$180,000"
    assert len(jobs[0]["description"]) <= 1200
    # And the filter now actually enforces the floor on it:
    matches, stats = filter_jobs([_job(salary=jobs[0]["salary"])], CONFIG)
    assert len(matches) == 0 and stats["salary_too_low"] == 1


def test_greenhouse_without_pay_still_unlisted():
    payload = {"jobs": [{"id": 2, "title": "Senior Product Designer",
                         "location": {"name": "Remote"}, "absolute_url": "https://x",
                         "updated_at": "2026-11-01", "content": "&lt;p&gt;No pay info&lt;/p&gt;"}]}
    with patch("sources.requests.get", return_value=_fake_get(payload)):
        jobs = fetch_greenhouse({"greenhouse_companies": ["testco"]})
    assert jobs[0]["salary"] == ""


def test_ashby_uses_compensation_summary():
    payload = {"jobs": [{"id": "a", "title": "Senior Product Designer", "location": "Remote",
                         "jobUrl": "https://x", "publishedAt": "2026-11-01",
                         "descriptionHtml": "<p>Join us</p>",
                         "compensation": {"scrapeableCompensationSalarySummary": "$204K - $264K"}}]}
    with patch("sources.requests.get", return_value=_fake_get(payload)) as g:
        jobs = fetch_ashby({"ashby_companies": ["testco"]})
    assert "includeCompensation=true" in g.call_args[0][0]
    assert jobs[0]["salary"] == "$204,000–$264,000"


def test_ashby_missing_compensation_falls_back_to_description():
    payload = {"jobs": [{"id": "b", "title": "Senior Product Designer", "location": "Remote",
                         "jobUrl": "https://x", "publishedAt": "2026-11-01",
                         "descriptionHtml": "<p>Base pay: $190,000 – $230,000</p>",
                         "compensation": None}]}
    with patch("sources.requests.get", return_value=_fake_get(payload)):
        jobs = fetch_ashby({"ashby_companies": ["testco"]})
    assert jobs[0]["salary"] == "$190,000–$230,000"


def test_lever_salary_range_and_text_fallback():
    assert _lever_salary({"salaryRange": {"min": 180000, "max": 220000,
                                          "interval": "per-year-salary"}}) == "$180,000–$220,000"
    assert _lever_salary({"salaryRange": {"min": 80, "max": 90, "interval": "per-hour-wage"},
                          "additionalPlain": "No annual range listed"}) == ""
    assert _lever_salary({"lists": [{"text": "Pay", "content": "<li>$170,000 - $210,000</li>"}]}) \
        == "$170,000–$210,000"


def test_jobspy_salary_annualizes_and_handles_nan():
    nan = float("nan")
    assert _jobspy_salary({"min_amount": 200000, "max_amount": 240000, "interval": "yearly"}) \
        == "$200,000–$240,000"
    assert _jobspy_salary({"min_amount": 90, "max_amount": 110, "interval": "hourly"}) \
        == "$187,200–$228,800"
    assert _jobspy_salary({"min_amount": nan, "max_amount": 220000, "interval": "yearly"}) \
        == "$220,000–$220,000"
    assert _jobspy_salary({"min_amount": nan, "max_amount": nan, "interval": nan}) == ""
    assert _jobspy_salary({"min_amount": 90, "max_amount": 110, "interval": None}) == ""


def test_safe_salary_never_raises():
    assert _safe_salary(12345) == ""  # wrong type — swallowed, not a crash


# ── Broadened search: leadership titles, word boundaries, non-US remote,
#    unleveled high-pay roles. Uses config.example.yaml (the starting
#    point everyone gets) with a few search values filled in.

import yaml as _yaml
REAL = _yaml.safe_load(open(Path(__file__).resolve().parent.parent / "config.example.yaml"))
REAL.update({"locations": ["chicago", "remote"], "min_salary": 160000,
             "unleveled_min_salary": 225000})


def _passes(**kw):
    matches, stats = filter_jobs([_job(**kw)], REAL)
    return len(matches) == 1, stats


def test_leadership_titles_pass():
    for title in ["Head of Design", "Director, Product Design - AI & Context",
                  "Senior Director of Design, Search & Feeds", "Manager, Design - Systems",
                  "Senior Design Manager - Business Banking", "Design Leader, Emerging Products",
                  "Head of Product Design", "VP of Design", "Staff Experience Designer"]:
        ok, _ = _passes(title=title)
        assert ok, title


def test_sr_abbreviation_counts_as_senior():
    assert _passes(title="Sr. Product Designer, AI/BI")[0]
    assert _passes(title="Sr Product Designer")[0]


def test_ux_does_not_match_inside_words():
    ok, stats = _passes(title="Staff Engineer, Luxury")
    assert not ok and stats["no_title_match"] == 1


def test_intern_exclude_is_whole_word():
    assert _passes(title="Senior Product Designer, Internal Tools")[0]
    assert not _passes(title="Product Design Internship")[0]
    assert not _passes(title="Early Career, Product Designer (2027)")[0]


def test_non_design_manager_titles_still_dropped():
    assert not _passes(title="Global Design & Project Manager")[0]
    assert not _passes(title="Project Manager, Design and Construction")[0]
    assert not _passes(title="Manager, Software Engineering - UX Platform")[0]
    assert not _passes(title="Data Center Design Manager")[0]
    assert not _passes(title="Silicon Design Lead")[0]
    assert not _passes(title="UX Writer, Apple Ads", salary="$184,700–$277,600")[0]


def test_non_us_remote_dropped():
    for loc in ["Remote - Canada", "Remote UK", "Canada - Remote (ON, AB, BC, or NS Only)",
                "Remote, EMEA", "India - Remote"]:
        ok, stats = _passes(location=loc)
        assert not ok and stats["bad_location"] == 1, loc


def test_us_remote_and_mixed_locations_pass():
    for loc in ["Remote - US", "Remote U.S.", "United States - Remote", "Remote (US or Canada)",
                "Chicago, IL, New York, NY, or Remote within Canada or United States",
                "Remote - Chicago Area"]:
        assert _passes(location=loc)[0], loc


def test_unleveled_title_passes_when_pay_is_high():
    ok, _ = _passes(title="Product Designer, Growth", salary="$245,000–$310,000")
    assert ok
    matches, _ = filter_jobs([_job(title="Product Designer", salary="$190,000–$290,000")], REAL)
    assert "no level in title" in matches[0]["match_reason"]


def test_unleveled_title_dropped_when_pay_low_or_unlisted():
    for salary in ["$169,000–$214,000", ""]:
        ok, stats = _passes(title="Product Designer", salary=salary)
        assert not ok and stats["no_seniority"] == 1, salary


def test_unleveled_rule_off_when_not_configured():
    matches, _ = filter_jobs([_job(title="Product Designer", salary="$300,000")], CONFIG)
    assert matches == []


if __name__ == "__main__":
    # Fallback runner if pytest isn't installed
    import sys, traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError:
            failed += 1
            print(f"FAILED: {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
