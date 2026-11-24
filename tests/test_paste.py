"""Tests for "Add many at once": pasting a list of deadlines, one per line (deadline_agent/paste.py).

No API key and no internet needed. The clock is frozen at Thursday 5 Nov 2026, 10:00 AM.
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deadline_agent import paste, tools
from web import app as web_app

NOW = datetime(2026, 11, 5, 10, 0)
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def titles():
    return [deadline["title"] for deadline in tools.list_deadlines()["deadlines"]]


def rows(text):
    return [(row["title"], row["due"], row["subject"], row["ok"]) for row in paste.check(text)["rows"]]


# ---------- how a line is read ----------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Quiz 1, friday 5pm, Statistics", ("Quiz 1", "Friday 6 Nov 2026, 5:00 PM", "Statistics", True)),
        ("Essay | 20 dec | Academic Writing", ("Essay", "Sunday 20 Dec 2026, 11:59 PM", "Academic Writing", True)),
        ("Essay; 20 dec", ("Essay", "Sunday 20 Dec 2026, 11:59 PM", "", True)),
        ("Essay\t20 dec\tAcademic Writing", ("Essay", "Sunday 20 Dec 2026, 11:59 PM", "Academic Writing", True)),  # a spreadsheet
        ("Lab report due wednesday 9am", ("Lab report", "Wednesday 11 Nov 2026, 9:00 AM", "", True)),
        ("Lab report by wednesday 9am for Biology", ("Lab report", "Wednesday 11 Nov 2026, 9:00 AM", "Biology", True)),
        ("Essay - 20 dec", ("Essay", "Sunday 20 Dec 2026, 11:59 PM", "", True)),
        # The date itself holds a comma: the longest run of parts that is a date wins
        ("Quiz 2, 20 nov, 5pm, Statistics", ("Quiz 2", "Friday 20 Nov 2026, 5:00 PM", "Statistics", True)),
        # A dash in the title stays there, because the comma is tried first
        ("Lab 2 - Circuits, 20 nov", ("Lab 2 - Circuits", "Friday 20 Nov 2026, 11:59 PM", "", True)),
        # Bullets and numbers at the start are ignored
        ("- Quiz 3, 20 nov", ("Quiz 3", "Friday 20 Nov 2026, 11:59 PM", "", True)),
        ("• Quiz 3, 20 nov", ("Quiz 3", "Friday 20 Nov 2026, 11:59 PM", "", True)),
        ("12. Quiz 3, 20 nov", ("Quiz 3", "Friday 20 Nov 2026, 11:59 PM", "", True)),
        ("3) Quiz 3, 20 nov", ("Quiz 3", "Friday 20 Nov 2026, 11:59 PM", "", True)),
    ],
)
def test_each_way_of_writing_a_line(line, expected):
    assert rows(line) == [expected]


def test_week_numbers_work_with_a_chosen_session():
    tools.choose_session("NUS_AY2627_S2")
    [row] = paste.check("Lab, friday week 7 5pm, CS1010S")["rows"]
    assert row["due"] == "Friday 5 Mar 2027, 5:00 PM" and row["ok"]
    assert row["message"] == "That's week 7 of NUS AY2026/27 Semester 2 (Jan to May 2027)."


# ---------- lines that cannot be added ----------


def test_problems_are_explained_and_nothing_is_saved():
    tools.add_deadline("Old quiz", "20 nov")
    text = "\n".join(
        [
            "Title, Due, Subject",  # a header row copied from a spreadsheet
            "Old quiz, 21 nov",  # already saved
            "Essay, 20 dec",
            "essay, 21 dec",  # the same title twice in the list
            "Just some words",  # no separator and no "due"
            "Reflection, week 5",  # week numbers but no session chosen
            "Late, 1 nov 2026",  # in the past
        ]
    )
    result = paste.check(text)
    assert result["message"] == "1 of 7 lines are ready. Fix the others, or add the ready ones now."
    messages = [row["message"] for row in result["rows"]]
    assert messages[0].startswith("I couldn't work out a date from 'Due'.")
    assert messages[1] == "You already have a deadline called 'Old quiz'."
    assert messages[2] == "" and result["rows"][2]["ok"]
    assert messages[3] == "'essay' is in this list twice."
    assert messages[4] == paste.NO_SPLIT
    assert messages[5].startswith("To use week numbers like 'week 7', first choose your university")
    assert "already in the past" in messages[6]
    assert titles() == ["Old quiz"]  # checking never saves


@pytest.mark.parametrize("text", ["", "   \n\n ", None, 42, ["Quiz, friday"]])
def test_nothing_pasted(text):
    assert paste.check(text) == {"status": "error", "message": "Paste your deadlines first, one per line.", "rows": []}


def test_too_many_lines():
    text = "\n".join(f"Quiz {n}, 20 dec" for n in range(paste.MAX_LINES + 1))
    assert paste.check(text)["message"] == "Paste up to 100 lines at a time."


def test_a_very_long_line():
    [row] = paste.check("Quiz, 20 dec, " + "x" * 400)["rows"]
    assert not row["ok"] and row["message"] == "This line is longer than 300 characters."


# ---------- adding ----------


def test_add_saves_only_the_ready_lines_and_says_what_happened():
    result = paste.add("Quiz 1, friday 5pm, Statistics\nNo date here\nEssay, 20 dec")
    assert result["message"] == "Added 2 of 3 lines."
    assert [row["ok"] for row in result["rows"]] == [True, False, True]
    assert result["rows"][0]["message"] == "Saved 'Quiz 1', due Friday 6 Nov 2026, 5:00 PM."
    assert titles() == ["Quiz 1", "Essay"]
    saved = tools.list_deadlines()["deadlines"][0]
    assert saved["subject"] == "Statistics" and saved["due_date"] == "2026-11-06 17:00"


def test_add_refuses_sensitive_details_like_one_at_a_time_does():
    result = paste.add("Pay 4111 1111 1111 1111, friday")  # a test card number
    assert result["status"] == "error" and not result["rows"][0]["ok"]
    assert titles() == []


def test_adding_everything_says_so():
    assert paste.add("Quiz 1, friday 5pm\nEssay, 20 dec")["message"] == "Added 2 deadlines."


# ---------- the home page route ----------


@pytest.fixture
def client():
    app = FastAPI()
    web_app.add_groot(app)
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def test_the_route_checks_then_adds(client):
    checked = client.post("/groot/api/paste", json={"text": "Quiz 1, friday 5pm"}).json()
    assert checked["rows"][0]["ok"] and titles() == []
    added = client.post("/groot/api/paste", json={"text": "Quiz 1, friday 5pm", "save": True}).json()
    assert added["message"] == "Added 1 deadline." and titles() == ["Quiz 1"]


def test_only_a_real_true_adds(client):
    client.post("/groot/api/paste", json={"text": "Quiz 1, friday 5pm", "save": "yes"})
    assert titles() == []


def test_the_page_has_the_paste_box(client):
    page = client.get("/groot").text
    assert '<details id="paste-box" class="paste-box">' in page
    assert '<textarea id="paste-text" name="text" rows="6" spellcheck="false" aria-describedby="paste-hint"></textarea>' in page
