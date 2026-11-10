"""Tests for the spreadsheet tracker, setup helpers and settings."""
import csv
import os

import yaml

from tracker_csv import CsvTracker, COLUMNS
from setup_wizard import set_key, parse_money
from notion_client import page_id_from_link
from settings import load_env, save_env
from sources import filter_jobs


def _job(key="greenhouse:acme:1", title="Senior Product Designer"):
    return {"title": title, "company": "acme", "location": "Remote - US",
            "url": "https://example.com/1", "salary": "", "posted_date": "2026-11-01",
            "source": "Greenhouse", "match_reason": "because", "job_key": key}


def test_csv_tracker_creates_file_and_dedupes(tmp_path):
    t = CsvTracker(tmp_path / "applications.csv")
    assert t.existing_job_keys() == set()
    t.add_job(_job("k1"))
    t.add_job(_job("k2"), draft_text="Three bullets and an opener.")
    assert t.existing_job_keys() == {"k1", "k2"}
    with open(tmp_path / "applications.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == COLUMNS
    assert rows[0]["Status"] == "New" and rows[1]["Status"] == "Ready for Review"
    assert rows[0]["Salary"].startswith("unlisted")
    assert (tmp_path / "drafts" / "acme-senior-product-designer.txt").exists()


def test_csv_tracker_keeps_hand_edits(tmp_path):
    path = tmp_path / "applications.csv"
    t = CsvTracker(path)
    t.add_job(_job("k1"))
    # Simulate editing in a spreadsheet app, saved without a final newline.
    text = path.read_text(encoding="utf-8-sig").replace("New,", "Applied,", 1).rstrip("\r\n")
    path.write_text(text, encoding="utf-8-sig")
    t.add_job(_job("k2"))
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert [r["Status"] for r in rows] == ["Applied", "New"]
    assert [r["ID"] for r in rows] == ["k1", "k2"]


def test_set_key_replaces_block_and_flow_lists():
    text = "# hi\nlocations:\n  - \"a\"  # note\n  - \"b\"\nmin_salary: 5\n# ════ ADVANCED\nx: 1\n"
    out = set_key(text, "locations", ["chicago", "remote"])
    out = set_key(out, "min_salary", 150000)
    out = set_key(out, "tracker", "spreadsheet")
    data = yaml.safe_load(out)
    assert data == {"locations": ["chicago", "remote"], "min_salary": 150000,
                    "tracker": "spreadsheet", "x": 1}
    assert out.index("tracker") < out.index("# ════ ADVANCED")
    assert "# hi" in out


def test_example_config_round_trips_through_set_key():
    from setup_wizard import EXAMPLE_CONFIG
    text = EXAMPLE_CONFIG.read_text()
    for key in ("seniority_keywords", "locations", "greenhouse_companies"):
        text = set_key(text, key, ["x"])
    data = yaml.safe_load(text)
    assert data["locations"] == ["x"] and data["title_excludes"]


def test_parse_money():
    assert parse_money("150k") == 150000
    assert parse_money("$150,000") == 150000
    assert parse_money("0") == 0
    assert parse_money("lots") is None


def test_page_id_from_link():
    link = "https://www.notion.so/myspace/Job-hunt-0123456789abcdef0123456789abcdef?pvs=4"
    assert page_id_from_link(link) == "0123456789abcdef0123456789abcdef"
    assert page_id_from_link("not a link") is None


def test_env_file_round_trip(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.delenv("JS_TEST_KEY", raising=False)
    save_env({"JS_TEST_KEY": "abc"}, path)
    save_env({"JS_TEST_KEY": "def"}, path)
    assert path.read_text().count("JS_TEST_KEY") == 1
    monkeypatch.delenv("JS_TEST_KEY")
    load_env(path)
    assert os.environ["JS_TEST_KEY"] == "def"


def test_remote_only_counts_when_listed():
    base = {"title_keywords": ["product design"], "seniority_keywords": [],
            "min_salary": 0, "max_posting_age_days": 3650}
    job = dict(_job(), posted_date="")
    assert filter_jobs([dict(job)], {**base, "locations": ["remote"]})[0]
    assert not filter_jobs([dict(job)], {**base, "locations": ["chicago"]})[0]
    assert filter_jobs([dict(job)], {**base, "locations": []})[0]  # anywhere


def test_empty_seniority_means_any_level():
    cfg = {"title_keywords": ["product design"], "seniority_keywords": [],
           "locations": [], "min_salary": 0}
    matches, _ = filter_jobs([dict(_job(title="Product Designer"), posted_date="")], cfg)
    assert len(matches) == 1
