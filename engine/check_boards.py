"""Checks every company in config.yaml's greenhouse/lever/ashby lists
against the real job-board APIs. Usage: python engine/check_boards.py

For each company that 404s, it tries the other two providers and a few
common slug variants (e.g. "acme" -> "acmeai", "acme" -> "acmelabs")
and prints where the board actually lives, or that it isn't on any of
the three. Read-only: it never edits config.yaml. Copy the suggested
fixes in by hand.

Run it whenever you add companies to config.yaml. A wrong slug or the
wrong provider is the usual reason a company keeps 404ing.

Limitation: it can't guess names that differ completely from the
company name (a company whose board is named after its product). For those, find the slug
in the company's careers-page URL (jobs.ashbyhq.com/{slug},
jobs.lever.co/{slug}, job-boards.greenhouse.io/{slug}).
"""
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from settings import load_config

UA = {"User-Agent": "job-search-script/1.0"}

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}
CONFIG_KEYS = {"greenhouse": "greenhouse_companies",
               "lever": "lever_companies",
               "ashby": "ashby_companies"}
SUFFIXES = ("", "hq", "ai", "inc", "labs", "app", "work", "jobs")


def candidate_slugs(slug: str) -> list[str]:
    """The slug as given, then common variants, without duplicates."""
    bases = [slug]
    plain = slug.replace("-", "").replace("_", "")
    if plain != slug:
        bases.append(plain)
    out = []
    for base in bases:
        for suf in SUFFIXES:
            s = base + suf
            if s not in out:
                out.append(s)
    return out


def probe(ats: str, slug: str):
    """Returns the open-job count if the board exists, None if it
    doesn't, or raises on network errors (so a timeout is never
    mistaken for "board missing")."""
    resp = requests.get(ENDPOINTS[ats].format(slug), headers=UA, timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    return len(data) if isinstance(data, list) else len(data.get("jobs", []))


def resolve(ats: str, slug: str, probe_fn=probe) -> dict:
    """Checks the configured board first. If it's missing, searches
    every provider x slug variant and prefers a board with open jobs
    over an empty one."""
    try:
        count = probe_fn(ats, slug)
    except Exception as e:
        return {"status": "error", "ats": ats, "slug": slug, "detail": str(e)}
    # An empty board can mean the company switched providers and left
    # the old board behind, so look elsewhere before
    # calling it fine. Only switch if the other board has jobs.
    if count:
        return {"status": "ok", "ats": ats, "slug": slug, "jobs": count}

    found = []
    for other in ENDPOINTS:
        for cand in candidate_slugs(slug):
            if (other, cand) == (ats, slug):
                continue
            try:
                n = probe_fn(other, cand)
            except Exception:
                continue
            if n is not None:
                found.append({"ats": other, "slug": cand, "jobs": n})
    best = max(found, key=lambda f: f["jobs"]) if found else None
    if count == 0 and not (best and best["jobs"]):
        return {"status": "ok", "ats": ats, "slug": slug, "jobs": 0}
    if not best:
        return {"status": "missing", "ats": ats, "slug": slug}
    return {"status": "moved", "from_ats": ats, "from_slug": slug, **best}


def main():
    config = load_config()

    entries = [(ats, slug) for ats, key in CONFIG_KEYS.items()
               for slug in config.get(key) or []]
    print(f"Checking {len(entries)} company boards...\n")
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda e: resolve(*e), entries))

    ok = [r for r in results if r["status"] == "ok"]
    moved = [r for r in results if r["status"] == "moved"]
    missing = [r for r in results if r["status"] == "missing"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"OK ({len(ok)}):")
    for r in ok:
        note = "  <- board exists but has 0 open jobs" if r["jobs"] == 0 else ""
        print(f"  {r['ats']:<10} {r['slug']:<16} {r['jobs']:>4} jobs{note}")
    if moved:
        print(f"\nWRONG PROVIDER OR SLUG ({len(moved)}). Fix in config.yaml:")
        for r in moved:
            print(f"  {r['from_ats']}:{r['from_slug']:<14} -> {r['ats']}:{r['slug']}  ({r['jobs']} jobs)")
    if missing:
        print(f"\nNOT ON GREENHOUSE/LEVER/ASHBY ({len(missing)}). Remove, or find the slug by hand:")
        for r in missing:
            print(f"  {r['ats']}:{r['slug']}")
    if errors:
        print(f"\nNETWORK ERRORS ({len(errors)}). Not judged, rerun later:")
        for r in errors:
            print(f"  {r['ats']}:{r['slug']}  {r['detail']}")

    return 1 if (moved or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
