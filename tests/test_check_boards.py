"""Tests for check_boards.resolve — uses a fake probe, no network.
Run from the project folder: venv/bin/python -m pytest -q
"""
from check_boards import resolve, candidate_slugs


def fake_probe(boards):
    """boards: {(ats, slug): job_count}; anything else is a 404."""
    def probe(ats, slug):
        return boards.get((ats, slug))
    return probe


def test_working_board_is_left_alone():
    r = resolve("greenhouse", "globex", fake_probe({("greenhouse", "globex"): 12,
                                                    ("ashby", "globex"): 99}))
    assert r == {"status": "ok", "ats": "greenhouse", "slug": "globex", "jobs": 12}


def test_working_but_empty_board_is_still_ok():
    r = resolve("ashby", "initech", fake_probe({("ashby", "initech"): 0}))
    assert r["status"] == "ok" and r["jobs"] == 0


def test_wrong_provider_found():
    r = resolve("greenhouse", "hooli", fake_probe({("ashby", "hooli"): 138}))
    assert r["status"] == "moved"
    assert (r["from_ats"], r["ats"], r["slug"]) == ("greenhouse", "ashby", "hooli")


def test_slug_variant_found():
    r = resolve("ashby", "umbrella", fake_probe({("greenhouse", "umbrellaai"): 167}))
    assert (r["status"], r["ats"], r["slug"]) == ("moved", "greenhouse", "umbrellaai")


def test_prefers_board_with_jobs_over_empty_one():
    r = resolve("lever", "acme", fake_probe({("greenhouse", "acme"): 0,
                                              ("ashby", "acmehq"): 7}))
    assert (r["ats"], r["slug"]) == ("ashby", "acmehq")


def test_not_found_anywhere():
    r = resolve("greenhouse", "nowhereco", fake_probe({}))
    assert r["status"] == "missing"


def test_network_error_is_not_reported_as_missing():
    def boom(ats, slug):
        raise TimeoutError("timed out")
    r = resolve("greenhouse", "globex", boom)
    assert r["status"] == "error"


def test_candidate_slugs():
    c = candidate_slugs("piedpiper")
    assert c[0] == "piedpiper" and "piedpiperlabs" in c and "piedpiperai" in c
    assert len(c) == len(set(c))
    assert "examplecorp" in candidate_slugs("example-corp")


def test_empty_board_with_live_board_elsewhere_is_moved():
    # Example: old Ashby board still exists but is empty.
    r = resolve("ashby", "vandelay", fake_probe({("ashby", "vandelay"): 0,
                                                ("greenhouse", "vandelay"): 89}))
    assert (r["status"], r["ats"], r["slug"]) == ("moved", "greenhouse", "vandelay")


def test_empty_board_with_only_other_empty_boards_stays_put():
    r = resolve("ashby", "initech", fake_probe({("ashby", "initech"): 0,
                                              ("greenhouse", "initech"): 0}))
    assert (r["status"], r["ats"]) == ("ok", "ashby")
