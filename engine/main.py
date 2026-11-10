"""Finds new jobs and adds them to your tracker.

Usage (or just double-click "Find Jobs.command"):
  python engine/main.py             find jobs and add new ones to your tracker
  python engine/main.py --dry-run   preview matches; writes nothing, costs nothing

Steps: pull postings from every source -> keep the ones that match your
settings -> skip ones already in your tracker -> (optional) write a
tailored draft -> add them to your tracker. Every step prints a short
summary so you can see what happened.
"""
import sys

from settings import load_config, load_env, resolve_path
from sources import fetch_adzuna, fetch_greenhouse, fetch_lever, fetch_ashby, fetch_jobspy, filter_jobs
from tracker_csv import CsvTracker
from draft import drafting_key, load_portfolio_notes, generate_draft

DROP_LABELS = [
    ("no_title_match", "title isn't a match"),
    ("no_seniority", "level isn't a match"),
    ("excluded_title", "excluded title word"),
    ("bad_location", "location isn't a match"),
    ("too_old", "posted too long ago"),
    ("salary_too_low", "pay below your minimum"),
]


def get_tracker(config: dict):
    """The spreadsheet by default; Notion if chosen and set up."""
    if (config.get("tracker") or "spreadsheet").lower() == "notion":
        from notion_client import NotionTracker, NotionNotConfigured
        try:
            return NotionTracker(config)
        except NotionNotConfigured as e:
            print(f"Note: {e}")
            print("Saving to the spreadsheet instead for this run.\n")
    return CsvTracker(resolve_path(config.get("spreadsheet_path", "applications.csv")))


def fetch_all(config: dict) -> list[dict]:
    jobs = []
    for fetch in (fetch_adzuna, fetch_greenhouse, fetch_lever, fetch_ashby, fetch_jobspy):
        try:
            jobs += fetch(config)
        except Exception as e:  # one broken source never stops the run
            print(f"  [{fetch.__name__.removeprefix('fetch_')}] error, skipped: {e}")
    return jobs


def main():
    dry_run = "--dry-run" in sys.argv
    load_env()
    config = load_config()

    print("=== Looking for jobs ===")
    jobs = fetch_all(config)
    print(f"Postings found: {len(jobs)}")

    print("\n=== Checking them against your settings ===")
    matches, stats = filter_jobs(jobs, config)
    print(f"Checked:  {stats['scanned']}")
    for key, label in DROP_LABELS:
        if stats.get(key):
            print(f"  skipped, {label}: {stats[key]}")
    print(f"Matches:  {len(matches)}")

    if not matches:
        print("\nNo matching jobs this time. If that keeps happening, try a wider")
        print("search: run Set Up.command again, or see 'Change your search' in the README.")
        return 0

    if dry_run:
        print("\n=== PREVIEW (nothing saved) ===")
        for job in matches:
            print(f"\n{job['company']}: {job['title']}")
            print(f"  {job['url']}")
            print(f"  why: {job['match_reason']}")
        print(f"\n{len(matches)} matches. Nothing was saved. Double-click Find Jobs to save them.")
        return 0

    tracker = get_tracker(config)
    existing = tracker.existing_job_keys()

    # Also skip repeats within this run (the same job can appear twice,
    # e.g. on two pages of results).
    seen = set()
    new_matches = []
    for j in matches:
        key = j.get("job_key", "")
        if key in existing or key in seen:
            continue
        seen.add(key)
        new_matches.append(j)

    print(f"Already in your tracker: {len(matches) - len(new_matches)}  |  New: {len(new_matches)}")
    if not new_matches:
        print("\nNothing new since last time.")
        return 0

    drafting = drafting_key(config) is not None
    notes = load_portfolio_notes(config) if drafting else ""
    print(f"\n=== Adding to {tracker.describe()} ===")
    added = 0
    for job in new_matches:
        draft_text = None
        note = ""
        if drafting:
            try:
                draft_text = generate_draft(job, notes, config)
            except Exception as e:
                # The job is still added, just without a draft.
                note = f"  (draft failed: {e})"
        try:
            tracker.add_job(job, draft_text)
        except PermissionError:
            print(f"\nCouldn't write to {tracker.describe()}. If it's open in another app,")
            print("close it and run Find Jobs again.")
            return 1
        added += 1
        print(f"  + {job['company']}: {job['title']}{note}")

    print(f"\nDone. Added {added} new job(s) to {tracker.describe()}.")
    if not drafting:
        print("Tip: add an Anthropic key (run Set Up.command) to get tailored resume")
        print("bullets and a cover letter opening with every job.")
    print("Double-click 'Open Tracker.command' to see them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
