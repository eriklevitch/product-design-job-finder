"""Notion users only. One-time cleanup: archives duplicate rows already in Notion.

This is separate from main.py's normal dedup, which only prevents new
duplicates going forward. Rows written before the Job Key fix (see
notion_client.py) don't have a Job Key, so this script instead groups
by (Title, Company) and archives every copy but the oldest.

Archiving is a soft delete: rows go to Notion's trash, not gone
forever. If this removes something it shouldn't have, restore it from
the database's trash in Notion within the usual retention window.

Usage:
  python3 engine/dedupe_notion.py --dry-run   # shows what would be archived, changes nothing
  python3 engine/dedupe_notion.py             # actually archives the duplicates
"""
import sys
from collections import defaultdict

from notion_client import NotionTracker
from settings import load_config, load_env


def main():
    dry_run = "--dry-run" in sys.argv

    load_env()
    config = load_config()

    tracker = NotionTracker(config)
    rows = tracker.list_all_rows()
    print(f"Fetched {len(rows)} total rows from Notion.")

    groups = defaultdict(list)
    for row in rows:
        key = (row["title"].lower(), row["company"].lower())
        groups[key].append(row)

    to_archive = []
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        # Keep the oldest (earliest created_time), archive the rest.
        group.sort(key=lambda r: r["created_time"])
        keep, *dupes = group
        to_archive.extend(dupes)

    if not to_archive:
        print("No duplicates found. Nothing to do.")
        return

    print(f"\nFound {len(to_archive)} duplicate row(s) to archive:")
    for row in to_archive:
        print(f"  - {row['company']} — {row['title']}  (created {row['created_time']})")

    if dry_run:
        print(f"\nDRY RUN — nothing archived. Rerun without --dry-run to actually clean these up.")
        return

    print()
    for row in to_archive:
        tracker.archive_page(row["id"])
        print(f"  ✓ archived: {row['company']} — {row['title']}")

    print(f"\nDone. Archived {len(to_archive)} duplicate row(s).")


if __name__ == "__main__":
    sys.exit(main())
