"""Tests for the home page's "Heads up" box, its Grades section and POST /groot/api/mark.

No API key and no internet needed. The Origin and content type checks for
/groot/api/mark are also covered by the CHANGES list in test_web.py.
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
SUBJECT = "41039 Programming Fundamentals"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


@pytest.fixture
def app():
    app = FastAPI()
    web_app.add_groot(app)
    return app


@pytest.fixture
def client(app):
    """A browser on Groot's own page."""
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def save(path, *rows):
    """Write whole deadline dicts straight to the file."""
    path.write_text(json.dumps(list(rows)), encoding="utf-8")


def deadline(title, due="2026-11-20", subject=SUBJECT, **extra):
    return {"title": title, "due_date": due, "subject": subject, "done": False, **extra}


def section(page: str, element_id: str) -> str:
    """The HTML from the tag with this id to the end of its </section> or the next </div></section>."""
    start = page.index(f'id="{element_id}"')
    end = page.index("</section>", start)
    return page[start:end]


def plain(piece: str) -> str:
    """The text of some HTML, with tags taken out and spaces squashed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", piece)).split())


# ---------- the Heads up box ----------


def test_heads_up_is_hidden_when_nothing_clashes(client, deadlines_file):
    save(deadlines_file, deadline("Exam"))
    page = client.get("/groot").text

    assert '<section id="heads-up" class="heads-up" aria-labelledby="heads-up-heading" hidden>' in page


def test_heads_up_shows_each_clash(client, deadlines_file):
    save(deadlines_file, deadline("41039 Exam", "2026-11-11 20:59"), deadline("41039 Programming Project", "2026-11-12"))
    page = client.get("/groot").text
    box = section(page, "heads-up")

    assert box.startswith('id="heads-up" class="heads-up" aria-labelledby="heads-up-heading">')  # not hidden
    assert plain(box).endswith(
        "Heads up Your 41039 Exam (Wed 11 Nov, 8:59 PM) and 41039 Programming Project (Thu 12 Nov, 11:59 PM)"
        " are only 27 hours apart. Consider starting work on 41039 Exam a few days early."
    )
    # The box comes before the Due soon list
    assert page.index('id="heads-up"') < page.index('id="due-soon-list"')


def test_heads_up_matches_get_reminders(client, deadlines_file):
    save(deadlines_file, deadline("A", "2026-11-09"), deadline("B", "2026-11-10"), deadline("C", "2026-11-14"))
    box = section(client.get("/groot").text, "heads-up")

    shown = [html.unescape(item) for item in re.findall(r"<li>(.*?)</li>", box)]
    assert shown == [clash["message"] for clash in tools.get_reminders()["clashes"]]


def test_heads_up_escapes_titles(client, deadlines_file):
    evil = "<script>alert(1)</script>"
    save(deadlines_file, deadline(evil, "2026-11-09"), deadline("B", "2026-11-10"))
    box = section(client.get("/groot").text, "heads-up")

    assert "<script>" not in box
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in box


# ---------- the Grades section ----------


def test_grades_with_no_deadlines(client):
    page = client.get("/groot").text

    assert "Add some deadlines first, then enter your marks here." in page
    assert 'id="mark-form"' not in page


def test_grades_has_the_honest_note(client):
    page = client.get("/groot").text
    assert "Some subjects also have minimum rules, for example at least 40% on the exam, that Groot cannot check" in page


def test_grades_form_lists_every_deadline(client, deadlines_file):
    save(deadlines_file, deadline("Exam", weight_percent=60), deadline("Quiz", "2026-11-10", "", weight_percent=40))
    page = client.get("/groot").text

    assert re.findall(r'<option value="(.*?)">', page) == ["Quiz", "Exam"]  # soonest first
    assert '<input id="mark-mark" name="mark_percent"' in page
    assert '<input id="mark-weight" name="weight_percent"' in page


def test_grades_summary_for_each_subject(client, deadlines_file):
    save(
        deadlines_file,
        deadline("Quiz", weight_percent=20, mark_percent=70, done=True),
        deadline("Project", weight_percent=30),
        deadline("Exam", weight_percent=50),
        deadline("Essay", subject="Writing"),
        deadline("Note", subject=""),  # no subject, so not in any summary
    )
    grades = plain(section(client.get("/groot").text, "grades"))

    assert (
        "41039 Programming Fundamentals Earned so far: 14% of the final mark. Still to come: 80%."
        " To get a Pass (50), you need an average of 45% on what is left."
        " To get a Credit (65), you need an average of 63.8% on what is left."
        " To get a Distinction (75), you need an average of 76.3% on what is left."
        " To get a High Distinction (85), you need an average of 88.8% on what is left."
        " Weights and marks for this subject"  # the table's caption for screen readers
        " Task Weight Mark Quiz 20% 70% Project 30% not set Exam 50% not set"
    ) in grades
    assert "Writing Earned so far: 0% of the final mark." in grades
    assert "1 item (Essay) has no weight" in grades  # the warning is shown
    assert "Note" not in grades.split("Save mark", 1)[1]  # only in the form's list


def test_grades_summary_shows_secured_and_not_reachable(client, deadlines_file):
    # 70 x 75% = 52.5 earned, so a Pass is safe, but an HD needs (85 - 52.5) / 30 = 108.4% on the exam
    save(deadlines_file, deadline("Assignments", weight_percent=70, mark_percent=75), deadline("Exam", weight_percent=30))
    page = client.get("/groot").text

    assert '<li class="band secured">You have already secured a Pass (50)' in page
    assert '<li class="band not_reachable">A High Distinction (85) is no longer reachable' in page


def test_grades_escapes_subjects_and_titles(client, deadlines_file):
    save(deadlines_file, deadline('<img src=x onerror=alert(1)>', subject="<b>Maths</b>", weight_percent=100))
    grades = section(client.get("/groot").text, "grades")

    assert "<img" not in grades and "<b>" not in grades
    assert "&lt;b&gt;Maths&lt;/b&gt;" in grades
    assert 'value="&lt;img src=x onerror=alert(1)&gt;"' in grades


# ---------- POST /groot/api/mark ----------


def test_mark_saves_a_mark(client, deadlines_file):
    save(deadlines_file, deadline("Exam", weight_percent=50))

    response = client.post("/groot/api/mark", json={"title": "Exam", "mark_percent": "72", "weight_percent": ""})

    assert response.status_code == 200
    assert response.json()["message"] == "Set your mark to 72% for 'Exam'. It is marked as done too."
    stored = json.loads(deadlines_file.read_text())[0]
    assert (stored["mark_percent"], stored["weight_percent"], stored["done"]) == (72, 50, True)


def test_mark_can_change_only_the_weight(client, deadlines_file):
    save(deadlines_file, deadline("Exam"))

    result = client.post("/groot/api/mark", json={"title": "Exam", "mark_percent": "", "weight_percent": "45.5"}).json()

    assert result["status"] == "success"
    assert json.loads(deadlines_file.read_text())[0]["weight_percent"] == 45.5


@pytest.mark.parametrize("data, words", [
    ({"title": "Exam", "mark_percent": "120"}, "mark_percent must be a number from 0 to 100"),
    ({"title": "Exam", "mark_percent": "abc"}, "mark_percent must be a number from 0 to 100"),
    ({"title": "Exam"}, "Tell me the mark"),
    ({"title": "Nope", "mark_percent": 50}, "couldn't find a deadline called 'Nope'"),
    ({"mark_percent": 50}, "couldn't find a deadline"),
])
def test_mark_explains_problems_and_changes_nothing(client, deadlines_file, data, words):
    save(deadlines_file, deadline("Exam"))
    before = deadlines_file.read_bytes()

    result = client.post("/groot/api/mark", json=data).json()

    assert result["status"] == "error"
    assert words in result["message"]
    assert deadlines_file.read_bytes() == before


def test_mark_from_another_site_is_refused(app, deadlines_file):
    save(deadlines_file, deadline("Exam"))
    before = deadlines_file.read_bytes()
    browser = TestClient(app, base_url=ORIGIN, headers={"Origin": "http://evil.example"})

    response = browser.post("/groot/api/mark", json={"title": "Exam", "mark_percent": 0})

    assert response.status_code == 403
    assert deadlines_file.read_bytes() == before


def test_mark_with_no_origin_is_refused(app, deadlines_file):
    save(deadlines_file, deadline("Exam"))
    response = TestClient(app, base_url=ORIGIN).post("/groot/api/mark", json={"title": "Exam", "mark_percent": 0})
    assert response.status_code == 403


def test_mark_needs_json(client, deadlines_file):
    save(deadlines_file, deadline("Exam"))
    response = client.post("/groot/api/mark", data={"title": "Exam", "mark_percent": "50"})
    assert response.status_code == 415


def test_the_page_after_a_mark_shows_it(client, deadlines_file):
    save(deadlines_file, deadline("Exam", weight_percent=100))
    client.post("/groot/api/mark", json={"title": "Exam", "mark_percent": 90})

    grades = plain(section(client.get("/groot").text, "grades"))

    assert "Earned so far: 90% of the final mark. Still to come: 0%." in grades
    assert "You have already secured a High Distinction (85)" in grades


# ---------- the drop box's save passes the weight through ----------


def test_save_passes_each_rows_weight(client, deadlines_file):
    rows = [
        {"title": "41039 Exam", "due_date": "2026-11-20 09:00", "subject": SUBJECT, "weight_percent": 50},
        {"title": "41039 Quiz", "due_date": "2026-11-21 09:00", "subject": SUBJECT, "weight_percent": None},
        {"title": "41039 Lab", "due_date": "2026-11-22 09:00", "subject": SUBJECT},  # an older page sends no weight
    ]

    result = client.post("/groot/api/save", json={"rows": rows}).json()

    assert result["message"] == "Saved 3 deadlines to your list."
    stored = json.loads(deadlines_file.read_text())
    assert stored[0]["weight_percent"] == 50
    assert "weight_percent" not in stored[1] and "weight_percent" not in stored[2]


def test_import_page_script_sends_the_weight():
    # The drop box's JavaScript must send each row's weight with the rows it saves
    script = (web_app.STATIC_DIR / "import.js").read_text(encoding="utf-8")
    assert "weight_percent: entry.row.weight_percent" in script


def test_home_page_script_refreshes_the_new_parts():
    script = (web_app.STATIC_DIR / "home.js").read_text(encoding="utf-8")
    assert '["heads-up", "due-soon-list", "deadline-table", "grades"]' in script
    assert 'post("/groot/api/mark"' in script
