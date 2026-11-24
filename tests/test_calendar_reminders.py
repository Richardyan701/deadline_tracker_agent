"""Tests for the calendar file's reminder times and the "export again" note.

Web pages cannot pop up a reminder while they are closed, so Groot puts the
reminders in the calendar file and the student's calendar app shows them.
The calendar app only has what was exported, so the home page says when
the deadlines have changed since the last export.
No API key and no internet needed. The clock is frozen at Thursday 5 Nov 2026, 10:00 AM.
"""

import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deadline_agent import tools
from web import app as web_app
from web import pages

NOW = datetime(2026, 11, 5, 10, 0)
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setenv("DEADLINES_ICS_FILE", str(tmp_path / "deadlines.ics"))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


@pytest.fixture
def client():
    app = FastAPI()
    web_app.add_groot(app)
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def alarms(calendar: str) -> list[tuple[str, str]]:
    """Each reminder in a calendar file as (TRIGGER, DESCRIPTION)."""
    lines = calendar.split("\r\n")
    return [
        (lines[i + 2].removeprefix("TRIGGER:"), lines[i + 3].removeprefix("DESCRIPTION:"))
        for i, line in enumerate(lines)
        if line == "BEGIN:VALARM"
    ]


# ---------- choosing ----------


def test_one_day_before_unless_changed():
    assert tools.chosen_reminders() == ["1d"]


def test_choosing_reminder_times():
    result = tools.choose_reminders(["30m", "1d", "5h"])  # any order
    assert result == {
        "status": "success",
        "message": "Your calendar will remind you 1 day, 5 hours and 30 minutes before each deadline. "
        "Export to calendar again to update it.",
    }
    assert tools.chosen_reminders() == ["1d", "5h", "30m"]  # longest first


def test_no_reminders():
    assert tools.choose_reminders([])["message"] == (
        "Reminders are off. Export to calendar again to update your calendar."
    )
    assert tools.chosen_reminders() == []


@pytest.mark.parametrize("bad", ["1d", ["2 days"], [1], None, {"1d": True}])
def test_anything_else_is_refused(bad):
    tools.choose_reminders(["5h"])
    assert tools.choose_reminders(bad) == {"status": "error", "message": "Choose reminder times from the list."}
    assert tools.chosen_reminders() == ["5h"]


def test_reminders_and_the_session_are_kept_side_by_side(deadlines_file):
    tools.choose_reminders(["1w"])
    tools.choose_session("AUT2027")
    tools.choose_reminders(["2d", "1h"])
    settings = json.loads(deadlines_file.with_name("groot_settings.json").read_text(encoding="utf-8"))
    assert settings == {"reminders": ["2d", "1h"], "session": "AUT2027"}


def test_a_broken_settings_file_gives_the_default(deadlines_file):
    deadlines_file.with_name("groot_settings.json").write_text('{"reminders": ["soon"]}', encoding="utf-8")
    assert tools.chosen_reminders() == ["1d"]


# ---------- the calendar file ----------


def test_every_reminder_time_in_the_file():
    tools.choose_reminders(list(tools.REMINDER_TIMES))
    tools.add_deadline("Essay", "20 nov 5pm")
    tools.export_calendar()
    calendar = tools._calendar_file().read_bytes().decode("utf-8")
    assert alarms(calendar) == [
        ("-P7D", "Essay is due in 1 week"),
        ("-P2D", "Essay is due in 2 days"),
        ("-P1D", "Essay is due tomorrow"),
        ("-PT5H", "Essay is due in 5 hours"),
        ("-PT1H", "Essay is due in 1 hour"),
        ("-PT30M", "Essay is due in 30 minutes"),
    ]


def test_no_reminders_in_the_file():
    tools.choose_reminders([])
    tools.add_deadline("Essay", "20 nov 5pm")
    tools.export_calendar()
    calendar = tools._calendar_file().read_bytes().decode("utf-8")
    assert "BEGIN:VALARM" not in calendar and "BEGIN:VEVENT" in calendar


# ---------- is the calendar up to date? ----------


def test_the_calendar_state_follows_each_change():
    assert tools.calendar_state() == "empty"
    tools.add_deadline("Essay", "20 nov 5pm")
    assert tools.calendar_state() == "never"
    tools.export_calendar()
    assert tools.calendar_state() == "current"
    tools.add_deadline("Quiz", "friday")
    assert tools.calendar_state() == "changed"  # added after the export
    tools.export_calendar()
    tools.edit_deadline("Quiz", new_due_date="saturday")
    assert tools.calendar_state() == "changed"  # moved
    tools.export_calendar()
    tools.mark_done("Quiz")
    assert tools.calendar_state() == "changed"  # finished, but still in the calendar app
    tools.export_calendar()
    tools.choose_reminders(["1d", "30m"])
    assert tools.calendar_state() == "changed"  # new reminder times
    tools.export_calendar()
    assert tools.calendar_state() == "current"
    tools.mark_done("Essay")
    assert tools.calendar_state() == "empty"


def test_the_note_keeps_fingerprints_not_deadlines(deadlines_file):
    tools.add_deadline("Secret project", "20 nov")
    tools.export_calendar()
    settings = deadlines_file.with_name("groot_settings.json").read_text(encoding="utf-8")
    assert "Secret" not in settings and "2026-11-20" not in settings


# ---------- the home page ----------


def test_the_page_says_when_to_export(client):
    assert '<p id="export-nudge" class="nudge" hidden></p>' in client.get("/groot").text  # nothing to export
    tools.add_deadline("Essay", "20 nov 5pm")
    assert "Export to calendar so your calendar app can remind you before each deadline." in client.get("/groot").text
    client.post("/groot/api/export", json={})
    assert '<p id="export-nudge" class="nudge" hidden></p>' in client.get("/groot").text
    tools.add_deadline("Quiz", "friday")
    assert "Your deadlines or reminder times changed since your last export." in client.get("/groot").text


def test_the_reminder_picker(client):
    client.post("/groot/api/reminders", json={"reminders": ["1d", "5h", "30m"]})
    page = client.get("/groot").text
    assert '<summary id="reminder-summary">Calendar reminders: 1 day, 5 hours and 30 minutes before</summary>' in page
    assert '<input type="checkbox" name="reminder" value="5h" checked>5 hours</label>' in page
    assert '<input type="checkbox" name="reminder" value="1w">1 week</label>' in page


def test_reminder_summary_when_off():
    assert pages.reminder_summary([]) == "Calendar reminders: off"


def test_the_route_refuses_another_website():
    app = FastAPI()
    web_app.add_groot(app)
    stranger = TestClient(app, base_url=ORIGIN, headers={"Origin": "https://evil.example"})
    assert stranger.post("/groot/api/reminders", json={"reminders": []}).status_code == 403
    assert tools.chosen_reminders() == ["1d"]


def test_the_short_privacy_line_with_the_details_folded_away(client):
    page = client.get("/groot").text
    assert "<p>Your deadlines stay on this computer. The chat and outline import use Gemini, so never type private details.</p>" in page
    assert '<details class="more"><summary>Privacy details</summary>' in page
