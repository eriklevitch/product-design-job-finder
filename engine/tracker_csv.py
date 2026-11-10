"""The default tracker: a spreadsheet file (applications.csv) that opens
in Excel, Numbers, Google Sheets or LibreOffice. No account needed.

The tool only ever ADDS rows to the bottom. It never changes or removes a
row, so whatever you type into Status, Date applied or Notes is safe.

A job is recognized by the "ID" column (last column). That's how the tool
knows not to add the same job twice, so leave that column alone. To hide a
job you don't want, set its Status to "Not interested" rather than deleting
the row (a deleted row may come back on the next run).
"""
import csv
import re
from datetime import date
from pathlib import Path

COLUMNS = [
    "Status", "Company", "Title", "Location", "Salary", "Posted", "Link",
    "Why it matched", "Draft", "Date found", "Date applied", "Notes",
    "Source", "ID",
]
STATUSES = ["New", "Ready for Review", "Applied", "Interview", "Offer",
            "Rejected", "Not interested"]
# Excel and Google Sheets cut cells off around 32k / 50k characters.
_CELL_MAX = 30000


class CsvTracker:
    def __init__(self, path: Path, drafts_dir: Path | None = None):
        self.path = Path(path)
        self.drafts_dir = Path(drafts_dir) if drafts_dir else self.path.parent / "drafts"

    def describe(self) -> str:
        return f"the spreadsheet {self.path.name}"

    def existing_job_keys(self) -> set[str]:
        if not self.path.exists():
            return set()
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            return {(row.get("ID") or "").strip() for row in csv.DictReader(f)} - {""}

    def add_job(self, job: dict, draft_text: str | None = None) -> None:
        """Appends one row. If there's a draft, it goes in the Draft column
        and into drafts/<company>-<title>.txt for easy copying."""
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        if not new_file:
            self._ensure_trailing_newline()
        row = {
            "Status": "Ready for Review" if draft_text else "New",
            "Company": job.get("company", ""),
            "Title": job.get("title", ""),
            "Location": job.get("location", ""),
            "Salary": job.get("salary") or "unlisted (check posting)",
            "Posted": job.get("posted_date", ""),
            "Link": job.get("url", ""),
            "Why it matched": job.get("match_reason", ""),
            "Draft": (draft_text or "")[:_CELL_MAX],
            "Date found": date.today().isoformat(),
            "Date applied": "",
            "Notes": "",
            "Source": job.get("source", ""),
            "ID": job.get("job_key", ""),
        }
        # utf-8-sig adds a marker so Excel shows accents and "–" correctly.
        with open(self.path, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
        if draft_text:
            self.drafts_dir.mkdir(exist_ok=True)
            (self.drafts_dir / _draft_filename(job)).write_text(
                f"{job.get('title', '')} at {job.get('company', '')}\n"
                f"{job.get('url', '')}\n\n{draft_text}\n", encoding="utf-8")

    def _ensure_trailing_newline(self) -> None:
        """Spreadsheet apps sometimes save without a final line break,
        which would glue the next row onto the last one."""
        with open(self.path, "rb+") as f:
            f.seek(-1, 2)
            if f.read(1) not in (b"\n", b"\r"):
                f.write(b"\r\n")


def _draft_filename(job: dict) -> str:
    raw = f"{job.get('company', '')}-{job.get('title', '')}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:80] or "job"
    return f"{slug}.txt"
