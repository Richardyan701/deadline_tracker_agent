"""Tests for the deadline tools.

These need no API key and no internet. Every test saves to its own temporary
file (through the DEADLINES_FILE variable), so your real deadlines.json is
never touched.
"""

import importlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from deadline_agent import tools

# Pretend "now" is Thursday 5 Nov 2026, 10:00
NOW = datetime(2026, 11, 5, 10, 0)


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Point the tools at a fresh temporary file and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def add_back_on_1_oct(monkeypatch, title, due_date):
    """Add a deadline as if it was 1 Oct, then go back to NOW.

    Adding a date that is already past is refused, so this is how a test
    gets a deadline that has passed since it was saved.
    """
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 10, 1, 9, 0))
    assert tools.add_deadline(title, due_date)["status"] == "success"
    monkeypatch.setattr(tools, "_now", lambda: NOW)


# ---------- add_deadline ----------


def test_add_deadline_saves_it():
    result = tools.add_deadline("Assignment 1", "2026-11-20", "Machine Learning")

    assert result["status"] == "success"
    assert result["deadline"] == {
        "title": "Assignment 1",
        "due_date": "2026-11-20",
        "subject": "Machine Learning",
        "done": False,
    }


def test_add_deadline_subject_is_optional():
    result = tools.add_deadline("Quiz", "2026-11-20")

    assert result["status"] == "success"
    assert result["deadline"]["subject"] == ""


def test_add_deadline_accepts_date_with_time():
    result = tools.add_deadline("Exam", "2026-11-20 14:30")

    assert result["status"] == "success"
    assert result["deadline"]["due_date"] == "2026-11-20 14:30"


@pytest.mark.parametrize(
    "bad_date",
    [
        "",
        "2026/11/20",  # wrong separator
        "2026-1-5",  # missing leading zeros
        "2026-13-01",  # month 13 does not exist
        "2026-02-30",  # 30 Feb does not exist
        "2026-11-20 25:00",  # hour 25 does not exist
        "2026-11-20 14:60",  # minute 60 does not exist
        "2026-11-20T14:30",  # we want a space, not a T
        "2026-11-20 2:30pm",
    ],
)
def test_add_deadline_rejects_bad_dates(bad_date, deadlines_file):
    result = tools.add_deadline("Assignment 1", bad_date)

    assert result["status"] == "error"
    assert tools.DATE_EXAMPLES in result["message"]
    assert not deadlines_file.exists()  # nothing was saved


def test_add_deadline_rejects_duplicate_title_ignoring_case():
    tools.add_deadline("Assignment 1", "2026-11-20")

    result = tools.add_deadline("  assignment 1 ", "2026-12-01")

    assert result["status"] == "error"
    assert "already" in result["message"]
    assert len(tools.list_deadlines()["deadlines"]) == 1


def test_add_deadline_rejects_empty_title():
    result = tools.add_deadline("   ", "2026-11-20")

    assert result["status"] == "error"


# ---------- list_deadlines ----------


def test_list_deadlines_when_empty():
    result = tools.list_deadlines()

    assert result["status"] == "success"
    assert result["deadlines"] == []


def test_list_deadlines_is_sorted_soonest_first():
    tools.add_deadline("Later", "2026-12-01")
    tools.add_deadline("Soonest", "2026-11-10")
    tools.add_deadline("Middle", "2026-11-20 09:00")

    titles = [d["title"] for d in tools.list_deadlines()["deadlines"]]

    assert titles == ["Soonest", "Middle", "Later"]


def test_list_deadlines_includes_done_ones():
    tools.add_deadline("Assignment 1", "2026-11-20")
    tools.mark_done("Assignment 1")

    deadlines = tools.list_deadlines()["deadlines"]

    assert len(deadlines) == 1
    assert deadlines[0]["done"] is True


# ---------- next_deadline ----------


def test_next_deadline_when_empty():
    result = tools.next_deadline()

    assert result["status"] == "success"
    assert result["deadline"] is None


def test_next_deadline_picks_the_soonest():
    tools.add_deadline("Later", "2026-12-01")
    tools.add_deadline("Soonest", "2026-11-10")

    result = tools.next_deadline()

    assert result["deadline"]["title"] == "Soonest"


def test_next_deadline_skips_done_ones():
    tools.add_deadline("Soonest", "2026-11-10")
    tools.add_deadline("Later", "2026-12-01")
    tools.mark_done("Soonest")

    assert tools.next_deadline()["deadline"]["title"] == "Later"


def test_next_deadline_skips_past_ones(monkeypatch):
    add_back_on_1_oct(monkeypatch, "Old", "2026-11-01")
    tools.add_deadline("Coming", "2026-11-30")

    assert tools.next_deadline()["deadline"]["title"] == "Coming"


def test_next_deadline_when_everything_is_past_or_done(monkeypatch):
    add_back_on_1_oct(monkeypatch, "Old", "2026-11-01")
    tools.add_deadline("Finished", "2026-11-30")
    tools.mark_done("Finished")

    assert tools.next_deadline()["deadline"] is None


def test_date_without_time_is_still_upcoming_later_today():
    # "now" is 5 Nov 10:00, so a deadline on 5 Nov is still coming up
    tools.add_deadline("Due today", "2026-11-05")

    assert tools.next_deadline()["deadline"]["title"] == "Due today"


def test_date_with_time_earlier_today_is_past(monkeypatch):
    add_back_on_1_oct(monkeypatch, "This morning", "2026-11-05 09:00")

    assert tools.next_deadline()["deadline"] is None


# ---------- delete_deadline ----------


def test_delete_deadline_removes_it():
    tools.add_deadline("Assignment 1", "2026-11-20")
    tools.add_deadline("Assignment 2", "2026-11-25")

    result = tools.delete_deadline("Assignment 1")

    assert result["status"] == "success"
    titles = [d["title"] for d in tools.list_deadlines()["deadlines"]]
    assert titles == ["Assignment 2"]


def test_delete_deadline_ignores_case():
    tools.add_deadline("Assignment 1", "2026-11-20")

    assert tools.delete_deadline("ASSIGNMENT 1")["status"] == "success"
    assert tools.list_deadlines()["deadlines"] == []


def test_delete_unknown_title_is_an_error():
    tools.add_deadline("Assignment 1", "2026-11-20")

    result = tools.delete_deadline("Nope")

    assert result["status"] == "error"
    assert len(tools.list_deadlines()["deadlines"]) == 1  # nothing was deleted


# ---------- mark_done ----------


def test_mark_done_sets_done():
    tools.add_deadline("Assignment 1", "2026-11-20")

    result = tools.mark_done("assignment 1")

    assert result["status"] == "success"
    assert tools.list_deadlines()["deadlines"][0]["done"] is True


def test_mark_done_unknown_title_is_an_error():
    result = tools.mark_done("Nope")

    assert result["status"] == "error"


# ---------- saving to the file ----------


def test_deadlines_survive_a_reload():
    tools.add_deadline("Assignment 1", "2026-11-20", "Maths")
    tools.add_deadline("Assignment 2", "2026-11-25")
    tools.mark_done("Assignment 2")

    # Reloading the module is like restarting the program: nothing is
    # remembered in memory, so the data must come back from the file.
    importlib.reload(tools)

    deadlines = tools.list_deadlines()["deadlines"]
    assert [(d["title"], d["done"]) for d in deadlines] == [
        ("Assignment 1", False),
        ("Assignment 2", True),
    ]


def test_every_change_is_written_to_the_file(deadlines_file):
    tools.add_deadline("Assignment 1", "2026-11-20")
    assert len(json.loads(deadlines_file.read_text())) == 1

    tools.mark_done("Assignment 1")
    assert json.loads(deadlines_file.read_text())[0]["done"] is True

    tools.delete_deadline("Assignment 1")
    assert json.loads(deadlines_file.read_text()) == []


def test_missing_file_means_no_deadlines(deadlines_file):
    assert not deadlines_file.exists()

    assert tools.list_deadlines()["deadlines"] == []
    assert not deadlines_file.exists()  # just looking does not create it


@pytest.mark.parametrize(
    "bad_content",
    [
        "this is not json {{{",
        "",
        '{"title": "a dict, not a list"}',
        '["just a string"]',
        '[{"title": "missing the other keys"}]',
        '[{"title": "T", "due_date": "tomorrow", "subject": "", "done": false}]',
    ],
)
def test_corrupted_file_starts_empty_and_recovers(bad_content, deadlines_file):
    deadlines_file.write_text(bad_content, encoding="utf-8")

    # Reading does not crash
    assert tools.list_deadlines()["deadlines"] == []
    assert tools.next_deadline()["deadline"] is None

    # Adding works and replaces the bad file with a good one
    assert tools.add_deadline("Fresh start", "2026-11-20")["status"] == "success"
    assert [d["title"] for d in tools.list_deadlines()["deadlines"]] == ["Fresh start"]


def test_default_file_is_next_to_the_package(monkeypatch):
    monkeypatch.delenv("DEADLINES_FILE")

    expected = Path(tools.__file__).parent.parent / "deadlines.json"

    assert tools._data_file() == expected
    assert expected.parent.joinpath("deadline_agent").is_dir()
