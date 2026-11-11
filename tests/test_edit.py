"""Tests for editing a deadline: the edit_deadline tool, POST /groot/api/edit and the Edit button.

No API key and no internet needed. The Origin and content type checks for
/groot/api/edit are also covered by the CHANGES list in test_web.py.
"""

import html
import json
import re
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deadline_agent import tools
from web import app as web_app

# Pretend "now" is Thursday 5 Nov 2026, 10:00 AM in Sydney
NOW = datetime(2026, 11, 5, 10, 0)
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Point the tools at a fresh temporary file and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


@pytest.fixture
def client():
    """A browser on Groot's own page."""
    app = FastAPI()
    web_app.add_groot(app)
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def save(path, *rows):
    path.write_text(json.dumps(list(rows)), encoding="utf-8")


def deadline(title, due="2026-11-20", subject="Maths", **extra):
    return {"title": title, "due_date": due, "subject": subject, "done": False, **extra}


def saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- the tool: one change at a time ----------


def test_rename_keeps_everything_else(deadlines_file):
    save(deadlines_file, deadline("Essay", weight_percent=30, mark_percent=70, done=True))

    result = tools.edit_deadline("essay", new_title="Final Essay")

    assert result["status"] == "success"
    assert result["message"] == "Updated 'Essay': renamed it to 'Final Essay'."
    assert saved(deadlines_file) == [
        {"title": "Final Essay", "due_date": "2026-11-20", "subject": "Maths", "done": True,
         "weight_percent": 30, "mark_percent": 70}
    ]


def test_new_due_date_is_worked_out_by_the_same_code_as_add(deadlines_file):
    save(deadlines_file, deadline("Quiz 2"))

    result = tools.edit_deadline("Quiz 2", new_due_date="next friday 5pm")

    assert result["message"] == "Updated 'Quiz 2': moved it to Friday 13 Nov 2026, 5:00 PM."
    assert saved(deadlines_file)[0]["due_date"] == "2026-11-13 17:00"


def test_a_date_in_a_later_year_is_pointed_out(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", new_due_date="20 jan")

    assert "(that's in 2027, not this year)" in result["message"]
    assert saved(deadlines_file)[0]["due_date"] == "2027-01-20"


def test_new_subject(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", new_subject="Physics")

    assert result["message"] == "Updated 'Quiz': set its subject to 'Physics'."
    assert saved(deadlines_file)[0]["subject"] == "Physics"


def test_remove_subject(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", remove_subject=True)

    assert result["message"] == "Updated 'Quiz': removed its subject."
    assert saved(deadlines_file)[0]["subject"] == ""


def test_three_changes_at_once(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", "Quiz 1", "tomorrow", "Physics")

    assert result["message"] == (
        "Updated 'Quiz': renamed it to 'Quiz 1', moved it to Friday 6 Nov 2026, 11:59 PM"
        " and set its subject to 'Physics'."
    )
    assert saved(deadlines_file) == [deadline("Quiz 1", "2026-11-06", "Physics")]


def test_result_has_the_updated_deadline(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", new_title="Quiz 1")

    assert result["deadline"] == deadline("Quiz 1")


# ---------- the tool: things that are refused, with nothing changed ----------


@pytest.mark.parametrize(
    "words, part_of_message",
    [
        ("next week", "I couldn't work out a date from 'next week'."),
        ("30 feb", "30 Feb 2027 doesn't exist"),
        ("9am", "which is already in the past"),
        ("5:30", "5:30"),
    ],
)
def test_a_bad_new_date_changes_nothing(deadlines_file, words, part_of_message):
    save(deadlines_file, deadline("Quiz"))
    before = deadlines_file.read_bytes()

    result = tools.edit_deadline("Quiz", new_title="Quiz 1", new_due_date=words)

    assert result["status"] == "error"
    assert part_of_message in result["message"]
    assert deadlines_file.read_bytes() == before  # the rename was not saved either


def test_new_title_of_another_deadline_is_refused(deadlines_file):
    save(deadlines_file, deadline("Quiz"), deadline("Essay"))
    before = deadlines_file.read_bytes()

    result = tools.edit_deadline("Quiz", new_title="  ESSAY ")

    assert result == {"status": "error", "message": "You already have a deadline called 'Essay'. Pick a different title."}
    assert deadlines_file.read_bytes() == before


def test_changing_only_upper_and_lower_case_is_allowed(deadlines_file):
    save(deadlines_file, deadline("quiz one"))

    result = tools.edit_deadline("quiz one", new_title="Quiz One")

    assert result["status"] == "success"
    assert saved(deadlines_file)[0]["title"] == "Quiz One"


def test_unknown_title(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Essay", new_title="Report")

    assert result["status"] == "error"
    assert saved(deadlines_file) == [deadline("Quiz")]


def test_nothing_to_change_is_an_error(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz")

    assert result == {"status": "error", "message": "Tell me what to change: the title, the due date or the subject."}


def test_a_new_subject_and_remove_subject_together_are_refused(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", new_subject="Physics", remove_subject=True)

    assert result["status"] == "error"
    assert saved(deadlines_file) == [deadline("Quiz")]


def test_the_same_values_change_nothing_and_do_not_rewrite_the_file(deadlines_file):
    save(deadlines_file, deadline("Quiz"))
    before = deadlines_file.read_bytes()

    result = tools.edit_deadline("Quiz", "Quiz", "2026-11-20", "Maths")

    assert result["status"] == "success"
    assert result["message"] == "'Quiz' already looks like that, so nothing changed."
    assert deadlines_file.read_bytes() == before


@pytest.mark.parametrize("bad", [5, ["Quiz"], {"a": 1}])
def test_odd_arguments_from_the_model_give_a_message_not_a_crash(deadlines_file, bad):
    save(deadlines_file, deadline("Quiz"))

    for result in (
        tools.edit_deadline(bad, new_title="X"),
        tools.edit_deadline("Quiz", new_title=bad),
        tools.edit_deadline("Quiz", new_due_date=bad),
        tools.edit_deadline("Quiz", new_subject=bad),
        tools.edit_deadline("Quiz", new_title="X", remove_subject="yes"),
    ):
        assert result["status"] == "error"
    assert saved(deadlines_file) == [deadline("Quiz")]


def test_none_means_keep(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    result = tools.edit_deadline("Quiz", None, "tomorrow", None)

    assert result["status"] == "success"
    assert saved(deadlines_file) == [deadline("Quiz", "2026-11-06")]


def test_line_breaks_in_a_new_title_become_spaces(deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    tools.edit_deadline("Quiz", new_title="Quiz\n  one")

    assert saved(deadlines_file)[0]["title"] == "Quiz one"


def test_an_overdue_deadline_can_be_renamed_without_touching_its_date(deadlines_file):
    save(deadlines_file, deadline("Essay", "2026-11-03"))

    result = tools.edit_deadline("Essay", new_title="Late Essay")

    assert result["status"] == "success"
    assert saved(deadlines_file) == [deadline("Late Essay", "2026-11-03")]


def test_a_failed_save_changes_nothing(deadlines_file, monkeypatch):
    save(deadlines_file, deadline("Quiz"))
    before = deadlines_file.read_bytes()

    def fail(deadlines):
        raise OSError("disk full")

    monkeypatch.setattr(tools, "_save_deadlines", fail)
    result = tools.edit_deadline("Quiz", new_title="Quiz 1")

    assert result["status"] == "error"
    assert "nothing has changed" in result["message"]
    assert deadlines_file.read_bytes() == before


# ---------- POST /groot/api/edit ----------


def test_api_edit_changes_title_date_and_subject(client, deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    response = client.post("/groot/api/edit", json={
        "title": "Quiz", "new_title": "Quiz 1", "due_date": "tomorrow 5pm", "subject": "Physics",
    })

    assert response.json()["status"] == "success"
    assert saved(deadlines_file) == [deadline("Quiz 1", "2026-11-06 17:00", "Physics")]


def test_api_edit_empty_date_keeps_the_date_and_empty_subject_removes_it(client, deadlines_file):
    save(deadlines_file, deadline("Essay", "2026-11-03"))  # overdue, so its date could not be typed again

    response = client.post("/groot/api/edit", json={
        "title": "Essay", "new_title": "Late Essay", "due_date": "", "subject": "",
    })

    assert response.json()["status"] == "success"
    assert saved(deadlines_file) == [deadline("Late Essay", "2026-11-03", "")]


def test_api_edit_without_a_subject_field_keeps_the_subject(client, deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    client.post("/groot/api/edit", json={"title": "Quiz", "new_title": "Quiz 1"})

    assert saved(deadlines_file) == [deadline("Quiz 1")]


def test_api_edit_passes_the_tools_error_message_on(client, deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    response = client.post("/groot/api/edit", json={"title": "Quiz", "due_date": "next week", "subject": "Maths"})

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "I couldn't work out a date from 'next week'." in response.json()["message"]
    assert saved(deadlines_file) == [deadline("Quiz")]


# ---------- the Edit button and the Edit box on the home page ----------


def test_every_deadline_has_an_edit_button_with_its_saved_values(client, deadlines_file):
    save(deadlines_file, deadline("Quiz", "2026-11-13 17:00"), deadline("Essay", done=True))

    page = client.get("/groot").text
    buttons = re.findall(r'<button type="button" class="secondary" data-edit data-title="([^"]*)" data-due="([^"]*)" data-subject="([^"]*)">', page)

    assert buttons == [("Quiz", "2026-11-13 17:00", "Maths"), ("Essay", "2026-11-20", "Maths")]


def test_the_edit_button_escapes_a_title_that_tries_to_be_html(client, deadlines_file):
    evil = '<script>alert(1)</script>" onmouseover="alert(2)'
    save(deadlines_file, deadline(evil, subject="</td><b>"))

    page = client.get("/groot").text

    assert "<script>alert(1)" not in page
    assert f'data-edit data-title="{html.escape(evil)}"' in page
    assert f'data-subject="{html.escape("</td><b>")}"' in page


def test_the_edit_box_is_on_the_page_once_and_outside_the_table(client, deadlines_file):
    save(deadlines_file, deadline("Quiz"))

    page = client.get("/groot").text

    assert page.count('<dialog id="edit-dialog"') == 1
    table_end = page.index("</table>")
    assert page.index('<dialog id="edit-dialog"') > table_end  # so redrawing the table keeps the box
