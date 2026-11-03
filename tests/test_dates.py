"""Tests for understanding due dates typed in the student's own words.

No API key and no internet needed. Every test sets the clock itself through
tools._now, so the results never depend on the real date.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from deadline_agent import tools

THURSDAY = datetime(2026, 11, 5, 10, 0)  # Thursday 5 Nov 2026, 10:00 AM
FRIDAY = datetime(2026, 11, 6, 10, 0)
SATURDAY = datetime(2026, 11, 7, 10, 0)
SUNDAY = datetime(2026, 11, 8, 10, 0)
MONDAY = datetime(2026, 11, 9, 10, 0)


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary file, never the real deadlines.json."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    return path


def add_at(monkeypatch, now, due_date):
    """Pretend it is `now`, then add a deadline. Returns the tool's result."""
    monkeypatch.setattr(tools, "_now", lambda: now)
    return tools.add_deadline("Task", due_date)


def saved_date(monkeypatch, now, due_date):
    """Add a deadline at `now` and return the due date that was saved."""
    result = add_at(monkeypatch, now, due_date)
    assert result["status"] == "success", result["message"]
    return result["deadline"]["due_date"]


# ---------- every phrase, on Thursday 5 Nov 2026 at 10:00 AM ----------


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("today", "2026-11-05"),
        ("tomorrow", "2026-11-06"),
        ("TOMORROW", "2026-11-06"),
        ("in 3 days", "2026-11-08"),
        ("in 1 day", "2026-11-06"),
        ("in a week", "2026-11-12"),
        ("in 2 weeks", "2026-11-19"),
        ("in 3 hours", "2026-11-05 13:00"),
        ("in an hour", "2026-11-05 11:00"),
        # weekdays
        ("friday", "2026-11-06"),
        ("fri", "2026-11-06"),
        ("next friday", "2026-11-13"),
        ("thursday", "2026-11-12"),  # today is Thursday, so it means next week's
        ("monday", "2026-11-09"),
        ("next monday", "2026-11-09"),
        ("wed", "2026-11-11"),
        # day and month (day comes first)
        ("20 nov", "2026-11-20"),
        ("20 Nov", "2026-11-20"),
        ("20th november", "2026-11-20"),
        ("20 november 2026", "2026-11-20"),
        ("3 jan 2027", "2027-01-03"),
        ("20/11", "2026-11-20"),
        ("20/11/2026", "2026-11-20"),
        ("5/11", "2026-11-05"),  # 5 November, which is today
        ("12/11", "2026-11-12"),  # 12 November, not 11 December
        ("1/12/2026", "2026-12-01"),  # 1 December
        # times on their own mean today
        ("5pm", "2026-11-05 17:00"),
        ("5 pm", "2026-11-05 17:00"),
        ("5:30pm", "2026-11-05 17:30"),
        ("5:30 PM", "2026-11-05 17:30"),
        ("11am", "2026-11-05 11:00"),
        ("17:00", "2026-11-05 17:00"),
        ("noon", "2026-11-05 12:00"),
        ("midday", "2026-11-05 12:00"),
        ("12pm", "2026-11-05 12:00"),
        ("midnight", "2026-11-05 23:59"),  # the end of today
        # a date and a time together
        ("next friday 5pm", "2026-11-13 17:00"),
        ("due next Friday 5pm", "2026-11-13 17:00"),
        ("Friday at 5:30pm", "2026-11-06 17:30"),
        ("5pm friday", "2026-11-06 17:00"),
        ("  next fri, 5pm  ", "2026-11-13 17:00"),
        ("in 3 days 9am", "2026-11-08 09:00"),
        ("20 nov 17:00", "2026-11-20 17:00"),
        ("20/11/2026 9:15am", "2026-11-20 09:15"),
        ("tomorrow 09:30", "2026-11-06 09:30"),
        ("tomorrow at noon", "2026-11-06 12:00"),
        ("tomorrow 12am", "2026-11-06 00:00"),  # 12am is the start of the day
        ("friday midnight", "2026-11-06 23:59"),
        # end of the week is Sunday, saved with no time (so 23:59)
        ("end of the week", "2026-11-08"),
        ("end of week", "2026-11-08"),
        ("end of this week", "2026-11-08"),
        ("end of next week", "2026-11-15"),
    ],
)
def test_phrases_on_a_thursday(monkeypatch, phrase, expected):
    assert saved_date(monkeypatch, THURSDAY, phrase) == expected


# ---------- "friday" vs "next friday" around the weekend ----------


@pytest.mark.parametrize(
    "now, phrase, expected",
    [
        # Today is Friday 6 Nov
        (FRIDAY, "friday", "2026-11-13"),  # never today, always the one after
        (FRIDAY, "next friday", "2026-11-13"),
        (FRIDAY, "saturday", "2026-11-07"),
        (FRIDAY, "next saturday", "2026-11-14"),
        (FRIDAY, "end of the week", "2026-11-08"),
        (FRIDAY, "end of next week", "2026-11-15"),
        # Today is Saturday 7 Nov
        (SATURDAY, "friday", "2026-11-13"),
        (SATURDAY, "next friday", "2026-11-13"),
        (SATURDAY, "sunday", "2026-11-08"),
        (SATURDAY, "next sunday", "2026-11-15"),
        (SATURDAY, "saturday", "2026-11-14"),
        (SATURDAY, "end of the week", "2026-11-08"),
        (SATURDAY, "end of next week", "2026-11-15"),
        # Today is Sunday 8 Nov, the last day of the week
        (SUNDAY, "sunday", "2026-11-15"),
        (SUNDAY, "next sunday", "2026-11-15"),
        (SUNDAY, "monday", "2026-11-09"),
        (SUNDAY, "next monday", "2026-11-09"),
        (SUNDAY, "friday", "2026-11-13"),
        (SUNDAY, "next friday", "2026-11-13"),
        (SUNDAY, "end of the week", "2026-11-08"),  # today
        (SUNDAY, "end of next week", "2026-11-15"),
        # Today is Monday 9 Nov, where the two are a week apart
        (MONDAY, "friday", "2026-11-13"),
        (MONDAY, "next friday", "2026-11-20"),
    ],
)
def test_weekdays_near_the_weekend(monkeypatch, now, phrase, expected):
    assert saved_date(monkeypatch, now, phrase) == expected


# ---------- crossing into a new month or year ----------


@pytest.mark.parametrize(
    "now, phrase, expected",
    [
        (datetime(2026, 11, 30, 10, 0), "in 3 days", "2026-12-03"),
        (datetime(2026, 12, 30, 10, 0), "in 3 days", "2027-01-02"),
        (datetime(2026, 12, 31, 10, 0), "tomorrow", "2027-01-01"),
        (datetime(2026, 12, 30, 10, 0), "in 2 weeks", "2027-01-13"),
        (datetime(2026, 12, 30, 10, 0), "friday", "2027-01-01"),
        (datetime(2026, 12, 30, 10, 0), "next monday", "2027-01-04"),
        (datetime(2026, 12, 30, 10, 0), "end of next week", "2027-01-10"),
        (datetime(2026, 12, 31, 22, 30), "in 3 hours", "2027-01-01 01:30"),
        (datetime(2026, 12, 30, 10, 0), "20 jan 2027", "2027-01-20"),
    ],
)
def test_month_and_year_rollover(monkeypatch, now, phrase, expected):
    assert saved_date(monkeypatch, now, phrase) == expected


# ---------- leap day ----------


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("tomorrow", "2028-02-29"),
        ("29 feb", "2028-02-29"),
        ("29/02/2028", "2028-02-29"),
        ("in 2 days", "2028-03-01"),
    ],
)
def test_leap_day_in_a_leap_year(monkeypatch, phrase, expected):
    monday_28_feb_2028 = datetime(2028, 2, 28, 10, 0)
    assert saved_date(monkeypatch, monday_28_feb_2028, phrase) == expected


@pytest.mark.parametrize("phrase", ["29 feb", "29/02/2027"])
def test_leap_day_that_does_not_exist(monkeypatch, phrase, deadlines_file):
    result = add_at(monkeypatch, THURSDAY, phrase)

    assert result["status"] == "error"
    assert "doesn't exist" in result["message"]
    assert not deadlines_file.exists()


def test_leap_day_with_the_year_is_fine(monkeypatch):
    assert saved_date(monkeypatch, THURSDAY, "29 feb 2028") == "2028-02-29"


# ---------- dates in the past ----------


@pytest.mark.parametrize(
    "phrase",
    [
        "today 9am",  # it is already 10:00
        "9am",
        "1 nov",  # this year's 1 Nov has passed, and we do not guess 2027
        "1/11",
        "20 nov 2025",
        "2026-11-01",
        "2026-11-05 09:00",
    ],
)
def test_past_dates_are_refused(monkeypatch, phrase, deadlines_file):
    result = add_at(monkeypatch, THURSDAY, phrase)

    assert result["status"] == "error"
    assert "in the past" in result["message"]
    assert "check" in result["message"]
    assert not deadlines_file.exists()


def test_past_message_shows_the_date_it_understood(monkeypatch):
    result = add_at(monkeypatch, THURSDAY, "1 nov")

    assert "Sunday 1 Nov 2026" in result["message"]


@pytest.mark.parametrize("phrase, expected", [("today 11am", "2026-11-05 11:00"), ("today", "2026-11-05")])
def test_later_today_is_fine(monkeypatch, phrase, expected):
    assert saved_date(monkeypatch, THURSDAY, phrase) == expected


def test_day_month_in_the_past_asks_for_the_year(monkeypatch):
    # On 30 Dec, "20 jan" means 20 Jan 2026, which has passed. We say so
    # instead of quietly picking 2027.
    result = add_at(monkeypatch, datetime(2026, 12, 30, 10, 0), "20 jan")

    assert result["status"] == "error"
    assert "add the year" in result["message"]


# ---------- unclear or impossible input ----------


@pytest.mark.parametrize(
    "phrase",
    [
        "banana",
        "",
        "   ",
        "due",
        "next",
        "next week",
        "soon",
        "the day after tomorrow",
        "fri 20 nov",
        "nov 20",
        "20/11/26",  # two digit year
        "20-11-2026",
        "in -3 days",
        "in 1000 days",
        "end of the week 5pm",
        "in 2 hours 5pm",
        "30 feb",
        "31/04",
        "32 nov",
        "20/13",
        "0/11",
        "13pm",
        "0am",
        "5:75pm",
        "25:00",
        "17:60",
        "5:30",  # morning or evening?
        "friday 9:00",
    ],
)
def test_unclear_or_impossible_input_is_refused(monkeypatch, phrase, deadlines_file):
    result = add_at(monkeypatch, THURSDAY, phrase)

    assert result["status"] == "error"
    assert "like" in result["message"]  # every error shows an example
    assert not deadlines_file.exists()


def test_impossible_date_names_the_date(monkeypatch):
    result = add_at(monkeypatch, THURSDAY, "30 feb")

    assert "30 Feb 2026 doesn't exist" in result["message"]


def test_morning_or_evening_question(monkeypatch):
    result = add_at(monkeypatch, THURSDAY, "friday 5:30")

    assert "am or pm" in result["message"]


# ---------- the success message echoes the date ----------


@pytest.mark.parametrize(
    "phrase, shown",
    [
        ("next friday 5pm", "Friday 13 Nov 2026, 5:00 PM"),
        ("20 nov", "Friday 20 Nov 2026, 11:59 PM"),
        ("tomorrow 12am", "Friday 6 Nov 2026, 12:00 AM"),
        ("noon", "Thursday 5 Nov 2026, 12:00 PM"),
        ("2026-12-01 09:05", "Tuesday 1 Dec 2026, 9:05 AM"),
    ],
)
def test_success_message_shows_the_date_in_full(monkeypatch, phrase, shown):
    result = add_at(monkeypatch, THURSDAY, phrase)

    assert result["message"] == f"Saved 'Task', due {shown}."


# ---------- the old task 1 formats and files still work ----------


@pytest.mark.parametrize(
    "typed, saved",
    [
        ("2026-11-20", "2026-11-20"),
        ("2026-11-20 14:30", "2026-11-20 14:30"),
        ("  2026-11-20  ", "2026-11-20"),
        ("2026-11-05", "2026-11-05"),  # today, due at 23:59
    ],
)
def test_iso_dates_are_saved_exactly_as_before(monkeypatch, typed, saved):
    assert saved_date(monkeypatch, THURSDAY, typed) == saved


def test_old_deadlines_file_still_loads(monkeypatch, deadlines_file):
    old = [
        {"title": "Essay", "due_date": "2026-11-20", "subject": "Writing", "done": False},
        {"title": "Exam", "due_date": "2026-11-10 09:00", "subject": "", "done": False},
        {"title": "Quiz", "due_date": "2026-10-01", "subject": "", "done": True},
    ]
    deadlines_file.write_text(json.dumps(old, indent=2), encoding="utf-8")
    monkeypatch.setattr(tools, "_now", lambda: THURSDAY)

    assert [d["title"] for d in tools.list_deadlines()["deadlines"]] == ["Quiz", "Exam", "Essay"]
    assert tools.next_deadline()["deadline"]["title"] == "Exam"

    # Adding a new one keeps the old ones exactly as they were
    assert tools.add_deadline("Lab", "next friday 5pm")["status"] == "success"
    saved = json.loads(deadlines_file.read_text(encoding="utf-8"))
    assert saved[:3] == old
    assert saved[3]["due_date"] == "2026-11-13 17:00"


# ---------- the real clock ----------


def test_now_is_sydney_time_without_a_timezone():
    now = tools._now()
    sydney = datetime.now(ZoneInfo("Australia/Sydney")).replace(tzinfo=None)

    assert now.tzinfo is None
    assert abs(now - sydney) < timedelta(seconds=5)
