"""Tests for Groot's home page and its JSON API (web/app.py and web/pages.py).

No API key and no internet needed. FastAPI's TestClient sends requests
straight to the app, the deadlines go to a temporary file (through the
DEADLINES_FILE variable) and the clock is frozen. Most tests put Groot's
routes on a small app of their own. The last tests use the real app from
build_app(), with ADK's chat on the same server.
"""

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google import genai

from deadline_agent import tools
from web import app as web_app

# Pretend "now" is Thursday 5 Nov 2026, 10:00 AM in Sydney
NOW = datetime(2026, 11, 5, 10, 0)

# The address a browser on Groot's own page sends in its Origin header
ORIGIN = "http://127.0.0.1:8000"

REFUSED_ORIGIN = {"status": "error", "message": "This request did not come from Groot's own page, so it was refused."}

# Every route that changes something, with a request it would accept
CHANGES = [
    ("/groot/api/add", {"title": "Quiz", "due_date": "friday", "subject": ""}),
    ("/groot/api/done", {"title": "Essay"}),
    ("/groot/api/delete", {"title": "Essay"}),
    ("/groot/api/edit", {"title": "Essay", "new_title": "Final Essay"}),
    ("/groot/api/mark", {"title": "Essay", "mark_percent": 80}),
    ("/groot/api/export", {}),
    ("/groot/api/save", {"rows": [{"title": "Quiz", "due_date": "friday", "subject": ""}]}),
]

# A title and a subject that try to sneak HTML and JavaScript onto the page
EVIL_TITLE = '<script>alert("title")</script><img src=x onerror=alert(1)> " onmouseover="alert(2)'
EVIL_SUBJECT = "</td><script>alert('subject')</script>"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary folder and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.delenv("DEADLINES_ICS_FILE", raising=False)
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


@pytest.fixture
def app():
    """Groot's routes on a small app of their own, without ADK's chat."""
    app = FastAPI()
    web_app.add_groot(app)
    return app


@pytest.fixture
def client(app):
    """A browser on Groot's own page: every request carries Groot's Origin header."""
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


@pytest.fixture
def no_gemini(monkeypatch):
    """Make any attempt to talk to Gemini fail the test.

    ADK's chat and the outline reader both reach Gemini through google.genai.Client.
    """

    def refuse(*args, **kwargs):
        raise AssertionError("something tried to make a Gemini client")

    monkeypatch.setattr(genai.Client, "__init__", refuse)


def save(path, *deadlines):
    """Write deadlines straight to the file, given as (title, due_date, subject, done).

    This skips add_deadline on purpose, because add_deadline refuses dates that
    have already passed and tidies titles.
    """
    rows = [{"title": t, "due_date": d, "subject": s, "done": done} for t, d, s, done in deadlines]
    path.write_text(json.dumps(rows), encoding="utf-8")


def saved(path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def part(page: str, element_id: str) -> str:
    """The HTML inside the <div> with this id, found by counting the <div> tags inside it."""
    start = page.index(f'<div id="{element_id}">') + len(f'<div id="{element_id}">')
    depth = 1
    for tag in re.finditer(r"<div\b|</div>", page[start:]):
        depth += 1 if tag[0] == "<div" else -1
        if depth == 0:
            return page[start : start + tag.start()]
    raise AssertionError(f"the <div> with id {element_id} is never closed")


def texts(piece: str, tag: str) -> list[str]:
    """The text inside each <tag> in a piece of HTML, with the inner tags taken out."""
    chunks = re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", piece, re.S)
    return [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", chunk)).split()) for chunk in chunks]


def table_rows(page: str) -> list[tuple]:
    """(state, title, status, buttons) for each row of the All deadlines table, top to bottom."""
    rows = []
    for state, row in re.findall(r'<tr class="(\w+)">(.*?)</tr>', part(page, "deadline-table"), re.S):
        title = html.unescape(re.search(r'<span class="title">(.*?)</span>', row)[1])
        status = re.search(r'<span class="status">(.*?)</span>', row)[1]
        rows.append((state, title, status, re.findall(r'data-action="(\w+)"', row)))
    return rows


class Tags(HTMLParser):
    """Every start tag on a page with its attributes, read the way a browser reads them."""

    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, dict(attrs)))


def tags(page: str) -> list[tuple]:
    parser = Tags()
    parser.feed(page)
    parser.close()
    return parser.found


# ---------- the home page ----------


def test_home_page_with_no_deadlines_shows_the_empty_state(client):
    page = client.get("/groot")

    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert "You have no deadlines saved yet." in part(page.text, "deadline-table")
    assert texts(part(page.text, "due-soon-list"), "p") == [
        "Good news, nothing is overdue and nothing is due in the next 7 days. You're all caught up!"
    ]
    assert "<table" not in page.text


def test_home_page_has_the_three_buttons(client):
    page = client.get("/groot").text

    assert '<button type="button" id="export-button">Export to calendar</button>' in page
    assert '<a class="button" href="/groot/import">Import from outlines</a>' in page
    assert '<a class="button" href="/dev-ui/?app=deadline_agent">Chat with Groot</a>' in page


def seed_a_week(path):
    save(
        path,
        ("Exam", "2026-11-13 09:00", "", False),  # in 8 days, too far for "due soon"
        ("Essay", "2026-11-06", "Writing", False),  # tomorrow, by 11:59 PM
        ("Lab report", "2026-11-03 17:00", "Physics", False),  # 2 days overdue
        ("Old essay", "2026-11-01", "Writing", True),  # finished
        ("Project", "2026-11-12 09:00", "", False),  # in 7 days
        ("Reading quiz", "2026-11-05 13:00", "", False),  # today, in 3 hours
    )


def test_due_soon_shows_overdue_today_and_this_week_with_friendly_phrases(client, deadlines_file):
    seed_a_week(deadlines_file)
    due_soon = part(client.get("/groot").text, "due-soon-list")

    # Reading quiz and Essay, and Project and Exam, are less than 48 hours apart, so the clash sentence is added
    assert texts(due_soon, "p") == [
        "Heads up, you have 1 overdue, 1 due today and 2 due in the next 7 days."
        " I also spotted 2 clashes where deadlines bunch up in the next 7 days."
    ]
    assert texts(due_soon, "li") == [
        "2 days overdue: Lab report Physics Due Tuesday 3 Nov 2026, 5:00 PM",
        "in 3 hours: Reading quiz Due Thursday 5 Nov 2026, 1:00 PM",
        "tomorrow: Essay Writing Due Friday 6 Nov 2026, 11:59 PM",
        "in 7 days: Project Due Thursday 12 Nov 2026, 9:00 AM",
    ]
    assert re.findall(r'<li class="(\w+)">', due_soon) == ["overdue", "due_today", "due_soon", "due_soon"]


def test_due_soon_matches_the_get_reminders_tool(client, deadlines_file):
    seed_a_week(deadlines_file)
    due_soon = part(client.get("/groot").text, "due-soon-list")

    shown = re.findall(r'<span class="when">(.*?):</span> <span class="title">(.*?)</span>', due_soon)
    reminders = tools.get_reminders()
    expected = [(item["when"], item["title"]) for group in ("overdue", "due_today", "due_soon") for item in reminders[group]]
    assert shown == expected


def test_all_deadlines_are_soonest_first_and_finished_ones_are_greyed(client, deadlines_file):
    seed_a_week(deadlines_file)
    page = client.get("/groot").text

    assert table_rows(page) == [
        ("done", "Old essay", "Done", ["delete"]),  # greyed, and nothing left to mark done
        ("overdue", "Lab report", "2 days overdue", ["done", "delete"]),
        ("upcoming", "Reading quiz", "in 3 hours", ["done", "delete"]),
        ("upcoming", "Essay", "tomorrow", ["done", "delete"]),
        ("upcoming", "Project", "in 7 days", ["done", "delete"]),
        ("upcoming", "Exam", "in 8 days", ["done", "delete"]),
    ]
    assert '<span class="due">Friday 6 Nov 2026, 11:59 PM</span>' in page


def test_buttons_say_which_deadline_they_are_for(client, deadlines_file):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False))
    page = client.get("/groot").text

    # The hidden words make a screen reader say "Mark done: Essay", not just "Mark done"
    assert 'Mark done<span class="visually-hidden">: Essay</span></button>' in page
    assert 'Delete<span class="visually-hidden">: Essay</span></button>' in page


def test_titles_and_subjects_are_escaped(client, deadlines_file):
    save(deadlines_file, (EVIL_TITLE, "2026-11-06 17:00", EVIL_SUBJECT, False))  # due tomorrow, so in both lists
    page = client.get("/groot").text
    found = tags(page)

    # The only script is Groot's own, nothing has an "on..." attribute, and no image was made
    assert [attrs.get("src") for tag, attrs in found if tag == "script"] == ["/groot/static/home.js"]
    assert not [tag for tag, _ in found if tag == "img"]
    assert not [name for _, attrs in found for name in attrs if name.startswith("on")]
    # The text is shown as it is: in both lists, on all three buttons (data-title and the hidden label),
    # and in the Grades section (the mark form's option value and label, the "no weight" warning
    # and the subject's table)
    escaped_title = "&lt;script&gt;alert(&quot;title&quot;)&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt; &quot; onmouseover=&quot;alert(2)"
    assert page.count(escaped_title) == 12
    # both lists, the Edit button's data-subject, and the subject's heading in the Grades section
    assert page.count("&lt;/td&gt;&lt;script&gt;alert(&#x27;subject&#x27;)&lt;/script&gt;") == 4
    # Each button gives the JavaScript back the exact title, and has no extra attributes
    buttons = [attrs for tag, attrs in found if tag == "button" and "data-action" in attrs]
    assert [(attrs["data-action"], attrs["data-title"]) for attrs in buttons] == [("done", EVIL_TITLE), ("delete", EVIL_TITLE)]
    assert all(attrs.keys() == {"type", "class", "data-action", "data-title"} for attrs in buttons)


def test_pages_tell_the_browser_to_run_only_groots_own_files(client):
    for path in ("/groot", "/groot/import"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy  # no other site can show the page inside a frame
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["cache-control"] == "no-store"


def test_the_home_page_trailing_slash_goes_to_the_home_page(client):
    response = client.get("/groot/", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (307, f"{ORIGIN}/groot")


# ---------- the browser files ----------


@pytest.mark.parametrize("name, content_type", list(web_app.STATIC_FILES.items()))
def test_browser_files_are_served_with_their_content_type(client, name, content_type):
    response = client.get(f"/groot/static/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == f"{content_type}; charset=utf-8"
    assert response.content == (web_app.STATIC_DIR / name).read_bytes()


@pytest.mark.parametrize("name", ["missing.js", "..%2fapp.py", "../app.py", "%2e%2e%2fapp.py"])
def test_only_the_listed_browser_files_are_served(client, name):
    assert client.get(f"/groot/static/{name}").status_code == 404


def test_browser_code_never_turns_text_into_html():
    # Text is always put on the page with textContent, which shows it as it is
    for name in web_app.STATIC_FILES:
        code = (web_app.STATIC_DIR / name).read_text(encoding="utf-8")
        for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            assert risky not in code, f"{name} uses {risky}"


# ---------- adding a deadline ----------


def test_add_goes_through_add_deadline(client, deadlines_file):
    result = client.post("/groot/api/add", json={"title": "Essay", "due_date": "next friday 5pm", "subject": "Writing"})

    assert result.status_code == 200
    assert result.json() == {
        "status": "success",
        "message": "Saved 'Essay', due Friday 13 Nov 2026, 5:00 PM.",
        "deadline": {"title": "Essay", "due_date": "2026-11-13 17:00", "subject": "Writing", "done": False},
    }
    assert saved(deadlines_file) == [{"title": "Essay", "due_date": "2026-11-13 17:00", "subject": "Writing", "done": False}]


def test_a_new_deadline_shows_up_on_the_home_page(client):
    client.post("/groot/api/add", json={"title": "Essay", "due_date": "20 nov", "subject": ""})
    assert table_rows(client.get("/groot").text) == [("upcoming", "Essay", "in 15 days", ["done", "delete"])]


@pytest.mark.parametrize(
    "data, message",
    [
        ({"title": "Essay", "due_date": "someday"}, "I couldn't work out a date from 'someday'. Try something like"),
        ({"title": "Essay", "due_date": "2026-11-01"}, "'2026-11-01' would be Sunday 1 Nov 2026, 11:59 PM, which is already in the past."),
        ({"title": "Essay", "due_date": "30 feb"}, "30 Feb 2027 doesn't exist"),
        ({"title": "Essay", "due_date": ""}, "Please tell me when it is due."),
        ({"title": "", "due_date": "friday"}, "A deadline needs a title."),
        ({"due_date": "friday"}, "A deadline needs a title."),
        ({"title": 5, "due_date": "friday"}, "title must be text, but I got 5."),
    ],
)
def test_add_shows_the_tools_own_error_message(client, deadlines_file, data, message):
    result = client.post("/groot/api/add", json=data).json()

    assert result["status"] == "error"
    assert result["message"].startswith(message)
    assert not deadlines_file.exists()


def test_add_refuses_a_title_that_is_already_used(client, deadlines_file):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False))
    result = client.post("/groot/api/add", json={"title": "  essay ", "due_date": "friday"}).json()
    assert result == {"status": "error", "message": "You already have a deadline called 'Essay'. Pick a different title."}


# ---------- mark done and delete ----------


def test_mark_done(client, deadlines_file):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "Writing", False))

    result = client.post("/groot/api/done", json={"title": "Essay"}).json()

    assert result == {"status": "success", "message": "Marked 'Essay' as done."}
    assert saved(deadlines_file)[0]["done"] is True
    assert table_rows(client.get("/groot").text) == [("done", "Essay", "Done", ["delete"])]


def test_delete(client, deadlines_file):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False), ("Quiz", "2026-11-21 09:00", "", False))

    result = client.post("/groot/api/delete", json={"title": "Essay"}).json()

    assert result == {"status": "success", "message": "Deleted 'Essay'."}
    assert [d["title"] for d in saved(deadlines_file)] == ["Quiz"]


@pytest.mark.parametrize("path", ["/groot/api/done", "/groot/api/delete"])
def test_done_and_delete_explain_an_unknown_title(client, deadlines_file, path):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False))
    before = deadlines_file.read_bytes()

    result = client.post(path, json={"title": "Nope"}).json()

    assert result["status"] == "error"
    assert result["message"].startswith("I couldn't find a deadline called 'Nope'.")
    assert deadlines_file.read_bytes() == before


def test_the_exact_title_from_a_button_finds_its_deadline(client, deadlines_file):
    # The page hands back data-title exactly, so even a title full of HTML can be deleted
    save(deadlines_file, (EVIL_TITLE, "2026-11-20 17:00", "", False))
    title = [attrs["data-title"] for tag, attrs in tags(client.get("/groot").text) if "data-title" in attrs][0]

    assert client.post("/groot/api/delete", json={"title": title}).json()["status"] == "success"
    assert saved(deadlines_file) == []


# ---------- export ----------


def test_export_downloads_deadlines_ics(client, deadlines_file):
    save(deadlines_file, ("Essay", "2026-11-20", "Writing", False), ("Lab 1", "2026-11-10", "", True))

    response = client.post("/groot/api/export", json={})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="deadlines.ics"'
    # It is the file export_calendar saved next to deadlines.json
    assert response.content == deadlines_file.with_name("deadlines.ics").read_bytes()
    assert response.content.startswith(b"BEGIN:VCALENDAR\r\n")
    assert b"SUMMARY:Essay\r\n" in response.content
    assert b"Lab 1" not in response.content  # finished, so left out


def test_export_with_nothing_unfinished_shows_the_tools_message(client, deadlines_file):
    save(deadlines_file, ("Lab 1", "2026-11-10", "", True))

    response = client.post("/groot/api/export", json={})

    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "success",
        "message": "You have no unfinished deadlines, so there is nothing to put in a calendar yet.",
        "exported": 0,
    }
    assert not deadlines_file.with_name("deadlines.ics").exists()


def test_export_that_cannot_save_shows_the_tools_message(client, deadlines_file, tmp_path, monkeypatch):
    save(deadlines_file, ("Essay", "2026-11-20", "", False))
    monkeypatch.setenv("DEADLINES_ICS_FILE", str(tmp_path / "no such folder" / "deadlines.ics"))

    result = client.post("/groot/api/export", json={}).json()

    assert result["status"] == "error"
    assert result["message"].startswith("I couldn't save your calendar file")


# ---------- only Groot's own page can change anything ----------


@pytest.mark.parametrize(
    "origin",
    [
        None,  # no Origin header at all
        "https://evil.example",
        "null",  # what a sandboxed frame or a file on disk sends
        "http://127.0.0.1:8001",  # another port is another site
        "https://127.0.0.1:8000",  # so is https
        "http://127.0.0.1:8000.evil.example",
    ],
)
@pytest.mark.parametrize("path, data", CHANGES)
def test_requests_from_anywhere_else_are_refused_and_change_nothing(app, deadlines_file, path, data, origin):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False))
    before = deadlines_file.read_bytes()
    browser = TestClient(app, base_url=ORIGIN, headers={} if origin is None else {"Origin": origin})

    response = browser.post(path, json=data)

    assert (response.status_code, response.json()) == (403, REFUSED_ORIGIN)
    assert deadlines_file.read_bytes() == before
    assert not deadlines_file.with_name("deadlines.ics").exists()


def test_localhost_is_groots_own_address_too(app, deadlines_file):
    browser = TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"})
    assert browser.post("/groot/api/add", json={"title": "Essay", "due_date": "friday"}).json()["status"] == "success"


@pytest.mark.parametrize(
    "content_type",
    [
        None,  # FastAPI would read a body with no content type as JSON, so it is refused on purpose
        "text/plain",  # what another site's page can send without asking first
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=groot",
        "application/jsonp",
    ],
)
@pytest.mark.parametrize("path, data", CHANGES)
def test_other_content_types_are_refused_and_change_nothing(client, deadlines_file, path, data, content_type):
    save(deadlines_file, ("Essay", "2026-11-20 17:00", "", False))
    before = deadlines_file.read_bytes()
    headers = {} if content_type is None else {"Content-Type": content_type}

    response = client.post(path, content=json.dumps(data).encode(), headers=headers)

    assert (response.status_code, response.json()) == (
        415,
        {"status": "error", "message": "Groot only accepts application/json here."},
    )
    assert deadlines_file.read_bytes() == before


def test_json_with_a_charset_is_fine(client):
    response = client.post(
        "/groot/api/add",
        content=b'{"title": "Essay", "due_date": "friday"}',
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert response.json()["status"] == "success"


@pytest.mark.parametrize(
    "body, message",
    [
        (b"{not json", "That request was not valid JSON."),
        (b'"\xff\xfe"', "That request was not valid JSON."),
        (b'["Essay"]', "That request must be a JSON object."),
    ],
)
def test_broken_json_is_refused(client, deadlines_file, body, message):
    response = client.post("/groot/api/add", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, response.json()) == (400, {"status": "error", "message": message})
    assert not deadlines_file.exists()


def test_reading_a_page_needs_no_origin(app, deadlines_file):
    # Pages only read, so a plain visit (which sends no Origin header) works
    assert TestClient(app, base_url=ORIGIN).get("/groot").status_code == 200


# ---------- the real app, with ADK's chat on the same server ----------


@pytest.mark.filterwarnings("ignore::UserWarning")  # ADK warns that some of its own parts are experimental
def test_groot_and_the_chat_share_one_server(no_gemini, deadlines_file):
    browser = TestClient(web_app.build_app(), base_url=ORIGIN, headers={"Origin": ORIGIN})

    assert browser.get("/groot").status_code == 200
    assert browser.get("/groot/import").status_code == 200
    chat = browser.get("/dev-ui/")
    assert chat.status_code == 200
    assert "<title>Agent Development Kit Dev UI</title>" in chat.text  # ADK's own chat page
    # The web folder is not mistaken for an agent, so the chat still only offers Groot
    assert browser.get("/list-apps").json() == ["deadline_agent"]
    # Changes still go through the tools, and nothing here talks to Gemini
    assert browser.post("/groot/api/add", json={"title": "Essay", "due_date": "friday"}).json()["status"] == "success"
    assert [d["title"] for d in saved(deadlines_file)] == ["Essay"]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_adks_guard_against_dns_rebinding_also_covers_groots_pages(deadlines_file):
    # A website that points its own name at 127.0.0.1 sends that name in the Host header
    browser = TestClient(web_app.build_app(), base_url="http://evil.example:8000")

    assert browser.get("/groot").status_code == 403
    response = browser.post("/groot/api/add", json={"title": "Essay", "due_date": "friday"}, headers={"Origin": "http://evil.example:8000"})
    assert response.status_code == 403
    assert not deadlines_file.exists()


def test_home_and_import_pages_warn_about_what_goes_to_gemini(client):
    # Students must be told before they use Groot that chats and outlines go to Google.
    home = client.get("/groot").text
    assert "go to Google's Gemini" in home and "student ID" in home
    importer = client.get("/groot/import").text
    assert "Privacy: outlines you preview are sent to Google's Gemini" in importer
