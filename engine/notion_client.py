"""Optional Notion tracker: dedup check, row creation, and building the
database itself.

You don't need to build the database by hand. Setup (Set Up.command)
asks for an integration token and a Notion page, then calls
create_database() below, which adds a database with every column this
tool uses (see DATABASE_PROPERTIES).

Dedup uses a "Job Key" property, not the URL. Some sources (Adzuna in
particular) issue a different tracking URL on every API call for the
same posting, so the URL alone isn't a reliable identifier — job_key
is built from each source's own stable internal job ID instead (see
sources.py). The URL column is still stored, it's just for display
and clicking through, not for dedup.
"""
import re

import requests

from settings import env
from tracker_csv import STATUSES

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def _raise_with_detail(resp):
    """requests' default HTTPError only says "400 Bad Request" with no
    context. Notion's actual error message (which property is wrong,
    why) is in the response body — surface it so failures are
    diagnosable from the terminal output alone."""
    if resp.ok:
        return
    try:
        detail = resp.json().get("message", resp.text)
    except ValueError:
        detail = resp.text
    raise requests.exceptions.HTTPError(
        f"{resp.status_code} error from Notion: {detail}", response=resp
    )


DATABASE_PROPERTIES = {
    "Title": {"title": {}},
    "Status": {"select": {"options": [{"name": s} for s in STATUSES]}},
    "Company": {"rich_text": {}},
    "Location": {"rich_text": {}},
    "Salary": {"rich_text": {}},
    "Posted Date": {"date": {}},
    "URL": {"url": {}},
    "Match Reason": {"rich_text": {}},
    "Date Applied": {"date": {}},
    "Source": {"select": {}},
    "Job Key": {"rich_text": {}},
}


class NotionNotConfigured(Exception):
    """Raised when the Notion keys aren't set; main.py falls back to the
    spreadsheet and explains why."""


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def page_id_from_link(link: str) -> str | None:
    """Pulls the 32-character page id out of a Notion link (or accepts a
    bare id). Returns None if there isn't one."""
    cleaned = link.strip().split("?")[0].split("#")[0].replace("-", "")
    found = re.findall(r"[0-9a-fA-F]{32}", cleaned)
    return found[-1].lower() if found else None


def create_database(token: str, parent_page_id: str, title: str = "Job applications") -> dict:
    """Creates the tracker database inside a page you've shared with your
    integration. Returns {"id": ..., "url": ...}."""
    resp = requests.post(
        f"{BASE_URL}/databases",
        headers=_headers(token),
        json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": DATABASE_PROPERTIES,
        },
        timeout=30,
    )
    _raise_with_detail(resp)
    data = resp.json()
    return {"id": data["id"], "url": data.get("url", "")}


class NotionTracker:
    def __init__(self, config):
        cfg = config.get("notion") or {}
        self.token = env(cfg.get("token_env", "NOTION_TOKEN"))
        self.database_id = env(cfg.get("database_id_env", "NOTION_DATABASE_ID"))
        if not self.token or not self.database_id:
            raise NotionNotConfigured(
                "Notion is selected as your tracker, but its keys aren't set. "
                "Run Set Up.command again and choose Notion.")
        self.headers = _headers(self.token)

    def describe(self) -> str:
        return "your Notion database"

    def url(self) -> str:
        return f"https://www.notion.so/{self.database_id.replace('-', '')}"

    def add_job(self, job: dict, draft_text: str | None = None) -> None:
        """Creates the row, then adds the draft as the page's content."""
        page_id = self.create_row(job, status="New")
        if draft_text:
            self.append_draft(page_id, draft_text)
            self.set_status(page_id, "Ready for Review")

    def _paginate_query(self, extra_payload: dict | None = None):
        """Yields all pages from the database query, handling pagination."""
        payload = {"page_size": 100, **(extra_payload or {})}
        while True:
            resp = requests.post(
                f"{BASE_URL}/databases/{self.database_id}/query",
                headers=self.headers, json=payload, timeout=30,
            )
            _raise_with_detail(resp)
            data = resp.json()
            yield from data["results"]
            if not data.get("has_more"):
                break
            payload["start_cursor"] = data["next_cursor"]

    def existing_job_keys(self) -> set[str]:
        """Pull every Job Key already tracked, for dedup. Paginates as
        needed. Rows without a Job Key simply aren't in this set
        (dedupe_notion.py can clean up duplicates among those)."""
        keys = set()
        for page in self._paginate_query():
            rich_text = page["properties"].get("Job Key", {}).get("rich_text", [])
            if rich_text:
                key = rich_text[0].get("plain_text", "").strip()
                if key:
                    keys.add(key)
        return keys

    def create_row(self, job: dict, status: str = "New") -> str:
        """Creates a new page/row. Returns the new page id."""
        props = {
            "Title": {"title": [{"text": {"content": job["title"][:200]}}]},
            "Company": {"rich_text": [{"text": {"content": job["company"][:200]}}]},
            "Location": {"rich_text": [{"text": {"content": job["location"][:200]}}]},
            "Salary": {"rich_text": [{"text": {"content": (job.get("salary") or "unlisted (check posting)")[:200]}}]},
            "Source": {"select": {"name": job["source"]}},
            "URL": {"url": job["url"]},
            "Job Key": {"rich_text": [{"text": {"content": job.get("job_key", "")[:200]}}]},
            "Match Reason": {"rich_text": [{"text": {"content": job["match_reason"][:2000]}}]},
            "Status": {"select": {"name": status}},
        }
        if job.get("posted_date"):
            props["Posted Date"] = {"date": {"start": job["posted_date"]}}

        resp = requests.post(
            f"{BASE_URL}/pages",
            headers=self.headers,
            json={"parent": {"database_id": self.database_id}, "properties": props},
            timeout=30,
        )
        _raise_with_detail(resp)
        return resp.json()["id"]

    def append_draft(self, page_id: str, draft_text: str):
        """Writes the generated draft as page content (blocks)."""
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": chunk}}]},
            }
            for chunk in _chunk_text(draft_text, 1900)
        ]
        resp = requests.patch(
            f"{BASE_URL}/blocks/{page_id}/children",
            headers=self.headers, json={"children": blocks}, timeout=30,
        )
        _raise_with_detail(resp)

    def set_status(self, page_id: str, status: str):
        resp = requests.patch(
            f"{BASE_URL}/pages/{page_id}",
            headers=self.headers,
            json={"properties": {"Status": {"select": {"name": status}}}},
            timeout=30,
        )
        _raise_with_detail(resp)

    def list_all_rows(self) -> list[dict]:
        """Every row with just the fields needed to spot duplicates:
        page id, title, company, and when it was created (so cleanup
        can keep the oldest copy of each duplicate group)."""
        rows = []
        for page in self._paginate_query():
            props = page["properties"]
            title_list = props.get("Title", {}).get("title", [])
            title = title_list[0].get("plain_text", "") if title_list else ""
            company_list = props.get("Company", {}).get("rich_text", [])
            company = company_list[0].get("plain_text", "") if company_list else ""
            rows.append({
                "id": page["id"],
                "title": title.strip(),
                "company": company.strip(),
                "created_time": page.get("created_time", ""),
            })
        return rows

    def archive_page(self, page_id: str):
        """Soft-deletes a page (moves it to Notion's trash — recoverable,
        not a permanent delete)."""
        resp = requests.patch(
            f"{BASE_URL}/pages/{page_id}",
            headers=self.headers,
            json={"archived": True},
            timeout=30,
        )
        _raise_with_detail(resp)


def _chunk_text(text: str, size: int):
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]
