"""Tests for the outline drop box: the import page, Preview and Save.

No API key and no internet needed. Most tests read outlines with a fake
reader instead of Gemini (swapped in through app.dependency_overrides). One
test runs the real outline reader with a fake Gemini client. The timetable
and Canvas readers are the real ones, given the same made-up timetable and
Canvas feed that their own tests use. Saving goes to a temporary file, so
your real deadlines.json is never touched.

Spring 2026 dates used below (from the UTS calendar): week 2 Friday is
7 Aug, week 3 Friday is 14 Aug, week 5 starts Monday 24 Aug.
"""

import asyncio
import json
import logging
import mimetypes
import sys
import tempfile
import types
from datetime import datetime

import httpx
import pytest
import starlette.formparsers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors
from starlette.datastructures import Headers
from test_canvas import LINK, SECRET, event, feed
from test_documents import DOC, FIXTURES, PPT, docx_file, odf_file, ole_file, picture, pptx_file, xlsx_file, zip_file
from test_timetable import FIXTURE, make_pdf

from deadline_agent import documents, importer, outline, tools
from web import app as web_app
from web import preview as web_preview
from web import uploads

# Pretend "now" is Monday 20 Jul 2026, the week before Spring starts
NOW = datetime(2026, 7, 20, 9, 0)
ORIGIN = "http://127.0.0.1:8000"
MB = 1024 * 1024


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary file and freeze the clock."""
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
    """A browser on Groot's own page: every request carries Groot's Origin header."""
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


@pytest.fixture
def no_gemini(monkeypatch):
    """Make any attempt to talk to Gemini fail the test."""

    def refuse(*args, **kwargs):
        raise AssertionError("something tried to make a Gemini client")

    monkeypatch.setattr(genai.Client, "__init__", refuse)


class Calls(list):
    """The outline files the fake reader was given, their names, and the function that gives its answer."""


@pytest.fixture
def reader(app):
    """Make Preview read outlines with a fake instead of Gemini.

    Returns the list of files (their bytes) the fake was given, and their
    names in reader.names. By default it finds one item per outline. Set
    reader.answer to a function to change that.
    """
    calls = Calls()
    calls.names = []

    def read(data: bytes, filename: str):
        calls.append(data)
        calls.names.append(filename)
        return calls.answer(data)

    calls.answer = lambda data: [item("Essay", "week", week=3)]
    app.dependency_overrides[web_app.outline_reader] = lambda: read
    return calls


@pytest.fixture
def fake_canvas(monkeypatch):
    """Make httpx.Client answer with a handler function instead of the internet. Returns the requests made."""
    real_client = httpx.Client
    requests = []

    def install(handler):
        def client(**settings):
            return real_client(transport=httpx.MockTransport(lambda request: requests.append(request) or handler(request)), **settings)

        monkeypatch.setattr(httpx, "Client", client)
        return requests

    return install


def item(name, when, code="33130", subject="Mathematics 1", **fields):
    """An outline item like the outline reader returns, with nothing set but what is given."""
    found = {
        "subject_code": code, "subject_name": subject, "name": name, "task_number": None,
        "weight_percent": None, "when": when, "date": None, "week": None, "first_week": None,
        "last_week": None, "weekday": None, "time": None, "quote": "",
    }
    found.update(fields)
    return found


def pdf(text: str) -> bytes:
    """Bytes that start like a PDF, which is all documents.py looks at to know it is one."""
    return b"%PDF-1.4\n" + text.encode() + b"\n%%EOF\n"


def preview(client, *outlines, timetable=None, canvas_url=None, session="SPR2026", extra=()):
    """Send the drop box form the way the page does. outlines are (file name, bytes) pairs."""
    # A browser sends a type it guesses from the name. Groot ignores it and looks at the bytes.
    files = [("outlines", (name, data, mimetypes.guess_type(name)[0] or "application/octet-stream")) for name, data in outlines]
    if timetable is not None:
        files.append(("timetable", ("timetable.pdf", timetable, "application/pdf")))
    files += list(extra)
    fields = {} if session is None else {"session": session}
    if canvas_url is not None:
        fields["canvas_url"] = canvas_url
    return client.post("/groot/api/preview", files=files, data=fields)


def without_due_text(rows):
    return [{key: value for key, value in row.items() if key != "due_text"} for row in rows]


# ---------- the import page ----------


def test_import_page_renders_with_every_input(client):
    page = client.get("/groot/import")

    assert page.status_code == 200
    text = page.text
    assert '<div id="drop-zone" class="drop-zone">' in text
    assert (
        f'<input id="outline-input" class="visually-hidden" type="file" accept="{documents.HTML_ACCEPT}" multiple'
        ' aria-describedby="outline-hint">'
    ) in text
    assert '<label for="outline-input" class="button">Choose outline files</label>' in text
    assert '<input id="timetable-input" type="file" accept=".pdf,application/pdf"' in text  # the timetable is still a PDF
    assert '<input id="canvas-input" type="url" autocomplete="off"' in text
    assert '<script type="module" src="/groot/static/import.js"></script>' in text


def test_the_drop_box_lists_every_kind_of_file_the_reader_reads(client):
    text = client.get("/groot/import").text

    # Both come straight from documents.py, so the page can never offer less or more than the reader does
    assert f'<p id="outline-hint" class="hint">1 to 8 outlines, each up to 10 MB. {documents.describe_supported()}</p>' in text
    assert documents.HTML_ACCEPT == ",".join(documents.SUPPORTED_EXTENSIONS)
    for ending in documents.SUPPORTED_EXTENSIONS:
        assert ending in documents.describe_supported()


def test_the_page_script_takes_its_file_endings_from_the_picker():
    # import.js checks dropped files against the picker's accept list, the one documents.py gives
    code = (web_app.STATIC_DIR / "import.js").read_text(encoding="utf-8")
    assert 'const ENDINGS = outlineInput.accept.split(",");' in code
    assert "is not a PDF" not in code


def test_the_session_picker_starts_on_spring_2026(client):
    text = client.get("/groot/import").text
    assert (
        '<select id="session-select"><option value="AUT2026">Autumn 2026</option>'
        '<option value="SPR2026" selected>Spring 2026</option></select>'
    ) in text


def test_the_page_warns_about_gemini_requests_before_preview(client):
    text = client.get("/groot/import").text
    warning = text.index("each outline uses one Gemini request. Gemini's free tier allows 20 requests a day")
    assert warning < text.index('id="preview-button"')  # the warning comes before the button


# ---------- preview ----------


def test_preview_rows_come_from_the_real_importer(client, reader, deadlines_file):
    found = [item("Skills Test 1", "week", week=2, weight_percent=10), item("Final exam", "exam_period", weight_percent=40)]
    reader.answer = lambda data: found

    response = preview(client, ("33130 outline.pdf", pdf("maths")))

    assert response.status_code == 200
    result = response.json()
    assert without_due_text(result["rows"]) == importer.build_preview(found, "SPR2026", now=NOW)
    assert [row["due_text"] for row in result["rows"]] == ["Friday 7 Aug 2026, 11:59 PM", ""]
    assert result["outlines"] == [{"file": "33130 outline.pdf", "status": "success", "message": "Found 2 assessment items."}]
    assert result["notes"] == []
    assert result["message"] == "Outlines read: 1 of 1. Check the 2 rows below, then save the ones you want."
    assert not deadlines_file.exists()  # Preview never saves anything


def test_each_outline_is_read_once_in_order(client, reader):
    reader.answer = lambda data: {
        pdf("maths"): [item("Skills Test 1", "week", week=2)],
        pdf("foundation"): [item("Quiz", "week", week=4, code="35010", subject="Foundation Mathematics")],
    }[data]

    result = preview(client, ("maths.pdf", pdf("maths")), ("foundation.pdf", pdf("foundation"))).json()

    assert reader == [pdf("maths"), pdf("foundation")]  # one Gemini request each
    assert reader.names == ["maths.pdf", "foundation.pdf"]
    assert [row["title"] for row in result["rows"]] == ["33130 Skills Test 1", "35010 Quiz"]


# One file of each kind documents.py reads, made the same way its own tests make them
EVERY_KIND = [
    ("maths.pdf", pdf("maths")),
    ("maths.docx", docx_file("33130 Mathematics 1", "Skills Test 1 is due in week 2")),
    ("old maths.doc", DOC),
    ("slides.pptx", pptx_file()),
    ("old slides.ppt", PPT),
    ("marks.xlsx", xlsx_file()),
    ("old marks.xls", (FIXTURES / "assessments.xls").read_bytes()),
    ("outline.odt", odf_file("text", "<text:p>Quiz 1 is due in week 3</text:p>")),
    ("slides.odp", odf_file("presentation", '<draw:page draw:name="1"><text:p>Quiz 1 in week 3</text:p></draw:page>')),
    ("marks.ods", odf_file("spreadsheet", "<table:table><table:table-row><table:table-cell><text:p>Quiz 1</text:p>"
                                          "</table:table-cell></table:table-row></table:table>")),
    ("marks.csv", b"Task,Weight,Due\nQuiz 1,10%,Week 3\n"),
    ("notes.txt", b"Quiz 1 is due in week 3"),
    ("notes.md", b"# Assessments\n- Quiz 1: week 3\n"),
    ("outline.html", b"<!DOCTYPE html><p>Quiz 1 is due in week 3</p>"),
    ("photo.png", picture("PNG")),
    ("photo.jpg", picture("JPEG")),
    ("scan.webp", picture("WEBP")),
]


def test_every_kind_of_file_the_reader_reads_is_accepted_with_its_name(client, reader):
    for start in range(0, len(EVERY_KIND), 8):  # at most 8 outlines in one upload
        response = preview(client, *EVERY_KIND[start : start + 8])
        assert response.status_code == 200, response.json()

    # Each file reaches the outline reader exactly as sent, with its name as the hint for documents.py
    assert reader == [data for _, data in EVERY_KIND]
    assert reader.names == [name for name, _ in EVERY_KIND]
    # Every kind documents.py reads is in the list above
    assert {documents.detect_kind(data, name) for name, data in EVERY_KIND} == set(documents.READERS) | set(documents.FILE_TYPES)


@pytest.mark.parametrize(
    "name, data",
    [
        ("outline.pdf", docx_file("Skills Test 1 is due in week 2")),  # a Word file with the wrong ending
        ("outline.docx", picture("PNG")),  # a picture with the wrong ending
        ("outline", pdf("maths")),  # no ending at all
    ],
)
def test_the_kind_comes_from_the_contents_not_the_name(client, reader, name, data):
    assert preview(client, (name, data)).status_code == 200
    assert reader.names == [name]


def test_the_timetable_gives_tutorial_days(client, reader):
    reader.answer = lambda data: [item("Skills Test 2", "tutorial", week=5)]

    result = preview(client, ("maths.pdf", pdf("maths")), timetable=make_pdf(FIXTURE.splitlines())).json()

    # The made-up timetable has 33130's Tut1 on Tuesdays at 9:00
    assert (result["rows"][0]["due_date"], result["rows"][0]["status"]) == ("2026-08-25 09:00", "exact")
    assert result["notes"] == ["Your timetable was read, so tutorial days come from it."]


def test_the_canvas_feed_is_merged_and_its_link_is_never_echoed_or_logged(client, reader, fake_canvas, caplog):
    caplog.set_level(logging.DEBUG)
    reader.answer = lambda data: [item("Skills Test 1", "week", week=7)]
    requests = fake_canvas(lambda request: httpx.Response(200, content=feed(event("Skills Test 1 [33130_SPR_U_1_S]", start="DTSTART:20260914T070000Z"))))

    response = preview(client, ("maths.pdf", pdf("maths")), canvas_url=LINK)

    row = response.json()["rows"][0]
    assert (row["due_date"], row["status"], row["source"]) == ("2026-09-14 17:00", "exact", "both")
    assert response.json()["notes"] == ["Your Canvas calendar was read (1 event)."]
    assert [str(request.url) for request in requests] == [LINK]  # fetched once
    assert SECRET not in response.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    "link, reason",
    [
        (f"http://canvas.uts.edu.au/feeds/calendars/{SECRET}.ics", "The Canvas link must start with https://."),
        (f"https://evil.example/{SECRET}.ics", "Only Canvas links from canvas.uts.edu.au or instructure.com can be used."),
    ],
)
def test_a_refused_canvas_link_is_explained_and_the_preview_goes_on(client, reader, fake_canvas, caplog, link, reason):
    requests = fake_canvas(lambda request: httpx.Response(200, content=feed()))

    response = preview(client, ("maths.pdf", pdf("maths")), canvas_url=link)

    assert response.status_code == 200
    assert response.json()["notes"] == [f"Your Canvas calendar was not used, so the preview went on without it. {reason}"]
    assert [row["title"] for row in response.json()["rows"]] == ["33130 Essay"]
    assert requests == []  # a refused link is never fetched
    assert SECRET not in response.text
    assert SECRET not in caplog.text


def test_a_damaged_canvas_feed_never_loses_the_outlines_already_read(client, reader, fake_canvas):
    # The Canvas feed is read after the outlines, so by then the Gemini requests are spent.
    # A feed the calendar library chokes on must not throw those results away.
    damaged = feed(event("Quiz [33130_SPR_U_1_S]", start="DTSTART;VALUE=,ATE:20260918"))
    fake_canvas(lambda request: httpx.Response(200, content=damaged))

    response = preview(client, ("maths.pdf", pdf("maths")), canvas_url=LINK)

    assert response.status_code == 200
    assert [row["title"] for row in response.json()["rows"]] == ["33130 Essay"]
    assert response.json()["notes"] == [
        "Your Canvas calendar was not used, so the preview went on without it. "
        "The Canvas link did not give a calendar. Copy the link again from Canvas, Calendar, Calendar Feed."
    ]
    assert len(reader) == 1


def test_a_damaged_timetable_is_explained_before_gemini(client, reader):
    damaged = make_pdf(FIXTURE.splitlines()).replace(b"trailer\n", b"trailer0", 1)

    response = preview(client, ("maths.pdf", pdf("maths")), timetable=damaged)

    assert (response.status_code, response.headers["content-type"]) == (400, "application/json")
    assert response.json()["message"] == (
        "Your timetable could not be used. The timetable could not be read as a PDF. "
        "Remove it or choose the right file, then try again. Nothing was sent to Gemini."
    )
    assert reader == []


def test_canvas_that_cannot_be_reached_is_explained(client, reader, fake_canvas):
    def handler(request):
        raise httpx.ConnectError(f"could not connect to {request.url}", request=request)

    fake_canvas(handler)
    response = preview(client, ("maths.pdf", pdf("maths")), canvas_url=LINK)

    assert response.json()["notes"] == [
        "Your Canvas calendar was not used, so the preview went on without it. "
        "Canvas could not be reached. Check your internet connection and try again."
    ]
    assert SECRET not in response.text


def test_an_outline_gemini_could_not_read_is_one_sentence_and_the_others_are_kept(client, reader):
    def answer(data):
        if data == pdf("busy"):
            raise web_preview.OutlineFailed("Gemini's free tier is busy. Wait a minute and try again.")
        return [item("Skills Test 1", "week", week=2)] if data == pdf("maths") else [item("Quiz", "week", week=4, code="35010")]

    reader.answer = answer
    result = preview(client, ("maths.pdf", pdf("maths")), ("busy.pdf", pdf("busy")), ("foundation.pdf", pdf("foundation"))).json()

    assert result["outlines"] == [
        {"file": "maths.pdf", "status": "success", "message": "Found 1 assessment item."},
        {"file": "busy.pdf", "status": "error", "message": "Gemini's free tier is busy. Wait a minute and try again."},
        {"file": "foundation.pdf", "status": "success", "message": "Found 1 assessment item."},
    ]
    assert len(reader) == 3  # the outline after the failed one was still read
    assert [row["title"] for row in result["rows"]] == ["33130 Skills Test 1", "35010 Quiz"]
    assert result["message"] == "Outlines read: 2 of 3. Check the 2 rows below, then save the ones you want."


def test_an_unexpected_error_is_one_sentence_and_never_a_stack_trace(client, reader, caplog):
    def answer(data):
        raise RuntimeError("Traceback (most recent call last): internal details")

    reader.answer = answer
    response = preview(client, ("maths.pdf", pdf("maths")))

    assert response.status_code == 200
    assert response.json()["outlines"] == [{"file": "maths.pdf", "status": "error", "message": web_preview.UNEXPECTED_PROBLEM}]
    assert "Traceback" not in response.text
    assert "internal details" not in response.text
    # The details go to the window where Groot runs, for whoever is fixing it
    assert "internal details" in caplog.text


def test_an_outline_with_no_assessments_says_so(client, reader):
    reader.answer = lambda data: []
    result = preview(client, ("blank.pdf", pdf("blank"))).json()

    assert result["outlines"] == [{"file": "blank.pdf", "status": "success", "message": "No assessments were found in this outline."}]
    assert result["rows"] == []
    assert result["message"] == "Outlines read: 1 of 1. Nothing was found to save."


def test_file_names_come_back_as_plain_data(client, reader):
    # The page shows them with textContent, so a name like this stays text
    name = "<img src=x onerror=alert(1)>.pdf"
    assert preview(client, (name, pdf("maths"))).json()["outlines"][0]["file"] == name


# ---------- the outline reader (deadline_agent/outline.py) ----------


def test_preview_says_the_outline_reader_is_not_installed_yet(client, monkeypatch, no_gemini):
    # None in sys.modules makes Python act as if outline.py were not there, even once it is added
    monkeypatch.setitem(sys.modules, "deadline_agent.outline", None)

    response = preview(client, ("maths.pdf", pdf("maths")))

    assert (response.status_code, response.json()) == (503, {"status": "error", "message": web_preview.READER_MISSING})
    assert "not installed yet" in web_preview.READER_MISSING


class FakeGemini:
    """Stands in for google.genai.Client inside the real outline reader. Answers each PDF from a dict."""

    def __init__(self, answers):
        self.answers = answers  # PDF bytes -> an answer dict, or an error to raise
        self.models = self

    def generate_content(self, *, model, contents, config):
        answer = self.answers[contents[0].inline_data.data]  # the PDF is the first part
        if isinstance(answer, Exception):
            raise answer
        return types.SimpleNamespace(text=json.dumps(answer))


def test_preview_with_the_real_outline_reader(client, monkeypatch, no_gemini):
    # Everything is real except Gemini itself. Swapping _default_client also means no .env file is read.
    week_2 = {"name": "Skills Test 1", "task_number": 1, "weight_percent": 10, "quote": "due in week 2", "when": "week",
              "date": None, "week": 2, "first_week": None, "last_week": None, "weekday": None, "time": None}
    busy = errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current quota."}})
    fake = FakeGemini({
        pdf("maths"): {"subject_code": "33130", "subject_name": "Mathematics 1", "items": [week_2]},
        pdf("foundation"): busy,
    })
    monkeypatch.setattr(outline, "_default_client", lambda: fake)

    result = preview(client, ("maths.pdf", pdf("maths")), ("foundation.pdf", pdf("foundation"))).json()

    assert result["outlines"] == [
        {"file": "maths.pdf", "status": "success", "message": "Found 1 assessment item."},
        {"file": "foundation.pdf", "status": "error", "message": outline.RATE_LIMIT_MESSAGE},
    ]
    assert [(row["title"], row["due_date"], row["status"]) for row in result["rows"]] == [
        ("33130 Skills Test 1", "2026-08-07 23:59", "assumed")
    ]


class FakeGeminiForText:
    """Stands in for google.genai.Client and keeps the outline text each request carried."""

    def __init__(self):
        self.texts = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.texts.append(contents[0].text)
        return types.SimpleNamespace(text=json.dumps({"subject_code": "33130", "subject_name": "Mathematics 1", "items": []}))


def test_the_file_name_reaches_the_real_outline_reader(client, monkeypatch, no_gemini):
    # A CSV file has nothing special in its bytes, so only its name tells documents.py to read it as a sheet
    fake = FakeGeminiForText()
    monkeypatch.setattr(outline, "_default_client", lambda: fake)
    csv_data = b"Task,Weight,Due\nSkills Test 1,10%,Week 2\n"

    result = preview(client, ("marks.csv", csv_data), ("notes.docx", docx_file("Skills Test 2 is in week 5"))).json()

    assert [entry["status"] for entry in result["outlines"]] == ["success", "success"]
    assert fake.texts == [
        f"{outline.TEXT_START}\nSheet: 1\nTask | Weight | Due\nSkills Test 1 | 10% | Week 2\n{outline.TEXT_END}",
        f"{outline.TEXT_START}\nSkills Test 2 is in week 5\n{outline.TEXT_END}",
    ]


def test_an_old_word_file_without_libreoffice_is_explained_without_a_gemini_request(client, monkeypatch, no_gemini):
    # The upload check only looks at what the file is. Turning a .doc into text needs LibreOffice,
    # and without it the outline gets documents.py's own sentence and nothing is sent.
    monkeypatch.setattr(documents.shutil, "which", lambda program: None)

    result = preview(client, ("old outline.doc", DOC)).json()

    assert result["outlines"] == [{"file": "old outline.doc", "status": "error", "message": documents.OLD_OFFICE_MESSAGE}]
    assert result["rows"] == []


def test_a_package_missing_inside_outline_py_is_not_hidden(monkeypatch):
    # Only outline.py itself being absent means "not installed yet". Anything else is a real error.
    def broken_import(name):
        raise ModuleNotFoundError("No module named 'pdfplumber'", name="pdfplumber")

    monkeypatch.setattr(web_preview.importlib, "import_module", broken_import)
    with pytest.raises(ModuleNotFoundError, match="pdfplumber"):
        web_preview.read_with_gemini(pdf("maths"), "maths.pdf")


# ---------- files that are refused before anything is sent to Gemini ----------


def outlines(count, size=None):
    return [(f"outline {number}.pdf", pdf(f"{number}") if size is None else b"%PDF-" + b"x" * (size - 5)) for number in range(count)]


def refused_outline(name, message):
    return f"{name}: {message} Nothing was sent to Gemini."


@pytest.mark.parametrize(
    "outline_files, options, status, message",
    [
        ([("notes.docx", b"PK\x03\x04 a Word file")], {}, 400, refused_outline("notes.docx", documents.DAMAGED_MESSAGE)),
        ([("empty.pdf", b"")], {}, 400, refused_outline("empty.pdf", documents.EMPTY_MESSAGE)),
        ([("photo.gif", picture("GIF"))], {}, 400, refused_outline("photo.gif", documents.UNKNOWN_MESSAGE)),
        ([("files.zip", zip_file({"notes.txt": "Quiz in week 3"}))], {}, 400, refused_outline("files.zip", documents.UNKNOWN_MESSAGE)),
        ([("outline.docm", docx_file("Quiz 1"))], {}, 400, refused_outline("outline.docm", documents.MACRO_MESSAGE)),
        ([("locked.docx", ole_file({"EncryptionInfo": b"i", "EncryptedPackage": b"s"}))], {}, 400,
         refused_outline("locked.docx", documents.LOCKED_MESSAGE)),
        # One bad file stops the whole upload before any outline is sent, even the good one before it
        (outlines(1) + [("photo.gif", picture("GIF"))], {}, 400, refused_outline("photo.gif", documents.UNKNOWN_MESSAGE)),
        (outlines(1), {"timetable": b"not a pdf"}, 400, "timetable.pdf is not a PDF, so nothing was read."),
        (outlines(1), {"timetable": docx_file("Tut1 Tuesday 9:00")}, 400, "timetable.pdf is not a PDF, so nothing was read."),
        ([("big.pdf", b"%PDF-" + b"x" * (10 * MB - 4))], {}, 413, "big.pdf is bigger than 10 MB, so nothing was read."),
        ([("big.docx", b"PK\x03\x04" + b"x" * (10 * MB - 3))], {}, 413, "big.docx is bigger than 10 MB, so nothing was read."),
        (outlines(1), {"timetable": b"%PDF-" + b"x" * (10 * MB - 4)}, 413, "timetable.pdf is bigger than 10 MB, so nothing was read."),
        (outlines(9), {}, 400, "At most 8 outlines can be read at a time. Remove some, then try again."),
        ([], {"timetable": pdf("timetable")}, 400, "Add at least one subject outline, then try again."),
        (outlines(1), {"session": None}, 400, "Choose a session, then try again."),
        (outlines(1), {"session": "SUM2026"}, 400, "Choose the session your outlines are for: Autumn 2026 or Spring 2026."),
        (
            outlines(1),
            {"timetable": pdf("a"), "extra": [("timetable", ("second.pdf", pdf("b"), "application/pdf"))]},
            400,
            "Only one timetable can be added at a time.",
        ),
        (outlines(1), {"extra": [("photo", ("me.pdf", pdf("c"), "application/pdf"))]}, 400, "The upload had a part Groot does not expect"),
        (outlines(1), {"canvas_url": "https://canvas.uts.edu.au/" + "x" * 3000}, 400, "Some text in the upload is too long"),
    ],
)
def test_bad_files_are_refused_before_gemini(client, reader, deadlines_file, outline_files, options, status, message):
    response = preview(client, *outline_files, **options)

    assert response.status_code == status
    assert response.json()["status"] == "error"
    assert response.json()["message"].startswith(message)
    assert reader == []  # nothing went to Gemini
    assert not deadlines_file.exists()


def test_a_timetable_that_is_not_a_uts_timetable_stops_before_gemini(client, reader):
    response = preview(client, ("maths.pdf", pdf("maths")), timetable=make_pdf(["My shopping list", "Milk"]))

    assert response.status_code == 400
    assert response.json()["message"] == (
        "Your timetable could not be used. No classes were found. Is this the PDF export of your UTS timetable? "
        "Remove it or choose the right file, then try again. Nothing was sent to Gemini."
    )
    assert reader == []


def test_exactly_8_outlines_are_accepted(client, reader):
    assert preview(client, *outlines(8)).status_code == 200
    assert len(reader) == 8


def test_an_outline_of_exactly_10_mb_is_accepted(client, reader):
    assert preview(client, *outlines(1, size=10 * MB)).status_code == 200
    assert [len(data) for data in reader] == [10 * MB]


def test_an_upload_that_is_cut_off_is_refused(client, reader):
    request = httpx.Request("POST", f"{ORIGIN}/groot/api/preview", files=[("outlines", ("a.pdf", pdf("a"), "application/pdf"))], data={"session": "SPR2026"})
    body = request.read()[:-20]  # the form's closing line is missing

    response = client.post("/groot/api/preview", content=body, headers={"Content-Type": request.headers["content-type"]})

    assert (response.status_code, response.json()["message"]) == (400, "The upload was cut off before the end, so please try again.")
    assert reader == []


def test_a_form_without_its_boundary_is_refused(client, reader):
    response = client.post("/groot/api/preview", content=b"--x--", headers={"Content-Type": "multipart/form-data"})
    assert (response.status_code, response.json()["message"]) == (400, "The upload was not a proper form, so it was not read.")


def test_uploads_are_never_written_to_disk(client, reader, monkeypatch):
    def no_disk(*args, **kwargs):
        raise AssertionError("an upload was written to disk")

    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, no_disk)
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", no_disk)

    # Bigger than the 1 MB that FastAPI's usual UploadFile keeps in memory
    big_outline = b"%PDF-" + b"x" * (5 * MB)
    response = preview(client, ("big.pdf", big_outline), timetable=make_pdf(FIXTURE.splitlines()))

    assert response.status_code == 200
    assert reader == [big_outline]

    # The trap really works: FastAPI's usual way of reading the same upload falls into it
    request = httpx.Request("POST", ORIGIN, files=[("outlines", ("big.pdf", big_outline, "application/pdf"))])

    async def body():
        yield request.read()

    usual_parser = starlette.formparsers.MultiPartParser(Headers({"content-type": request.headers["content-type"]}), body())
    with pytest.raises(AssertionError, match="written to disk"):
        asyncio.run(usual_parser.parse())


def test_the_upload_limits_match_the_spec():
    assert (uploads.MAX_FILE_BYTES, uploads.MAX_OUTLINES) == (10 * MB, 8)


# ---------- only Groot's own page can preview ----------


@pytest.mark.parametrize("origin", [None, "https://evil.example", "null"])
def test_preview_from_anywhere_else_is_refused_before_reading_anything(app, reader, origin):
    browser = TestClient(app, base_url=ORIGIN, headers={} if origin is None else {"Origin": origin})

    response = preview(browser, ("maths.pdf", pdf("maths")))

    assert response.status_code == 403
    assert reader == []  # another site cannot spend the student's Gemini requests


@pytest.mark.parametrize("content_type", ["application/json", "text/plain", "application/x-www-form-urlencoded", None])
def test_preview_only_accepts_a_multipart_form(client, reader, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}
    response = client.post("/groot/api/preview", content=b'{"session": "SPR2026"}', headers=headers)

    assert (response.status_code, response.json()["message"]) == (415, "Groot only accepts multipart/form-data here.")
    assert reader == []


# ---------- save ----------


def test_save_gives_one_result_per_row_and_a_bad_row_does_not_stop_the_others(client, deadlines_file):
    subject = "33130 Mathematics 1"
    rows = [
        {"title": "33130 Skills Test 1", "due_date": "2026-08-07 23:59", "subject": subject},
        {"title": "33130 Skills Test 1", "due_date": "2026-08-14 23:59", "subject": subject},  # the same title again
        {"title": "33130 Old quiz", "due_date": "2026-07-01 10:00", "subject": subject},  # in the past
        {"title": "33130 Final exam", "due_date": None, "subject": subject},  # no date
        {"title": "33130 Essay", "due_date": "2026-08-20 17:00", "subject": subject},
    ]

    result = client.post("/groot/api/save", json={"rows": rows}).json()

    assert [row["status"] for row in result["results"]] == ["success", "error", "error", "error", "success"]
    assert result["results"][0]["message"] == "Saved '33130 Skills Test 1', due Friday 7 Aug 2026, 11:59 PM."
    assert result["results"][1]["message"] == "You already have a deadline called '33130 Skills Test 1'. Pick a different title."
    assert "already in the past" in result["results"][2]["message"]
    assert result["results"][3]["message"].startswith("Please tell me when it is due.")
    assert result["message"] == "Saved 2 of 5 deadlines. Each row that was not saved says why."
    assert [d["title"] for d in json.loads(deadlines_file.read_text())] == ["33130 Skills Test 1", "33130 Essay"]


def test_a_needs_input_row_is_saved_once_the_student_types_a_date(client, reader, deadlines_file):
    reader.answer = lambda data: [item("Skills Test 2", "tutorial", week=5)]  # no timetable, so it needs a date
    row = preview(client, ("maths.pdf", pdf("maths"))).json()["rows"][0]
    assert (row["status"], row["due_date"], row["include"]) == ("needs_input", None, False)

    # The page sends the row back with the date the student typed into its cell
    typed = {"title": row["title"], "due_date": "25 aug 9am", "subject": row["subject"]}
    result = client.post("/groot/api/save", json={"rows": [typed]}).json()

    assert result["results"][0]["message"] == "Saved '33130 Skills Test 2', due Tuesday 25 Aug 2026, 9:00 AM."
    assert result["message"] == "Saved 1 deadline to your list."
    assert json.loads(deadlines_file.read_text()) == [
        {"title": "33130 Skills Test 2", "due_date": "2026-08-25 09:00", "subject": "33130 Mathematics 1", "done": False}
    ]


def test_a_typed_date_gets_add_deadlines_checks(client, deadlines_file):
    typed = {"title": "33130 Skills Test 2", "due_date": "sometime in week 5", "subject": "33130 Mathematics 1"}
    result = client.post("/groot/api/save", json={"rows": [typed]}).json()

    assert result["results"][0]["message"].startswith("I couldn't work out a date from 'sometime in week 5'.")
    assert not deadlines_file.exists()


def test_preview_rows_can_be_saved_as_they_are(client, reader, deadlines_file):
    reader.answer = lambda data: [item("Skills Test 1", "week", week=2), item("Essay", "date", date="2026-08-14", time="17:00")]
    rows = preview(client, ("maths.pdf", pdf("maths"))).json()["rows"]

    ticked = [{key: row[key] for key in ("title", "due_date", "subject")} for row in rows if row["include"]]
    result = client.post("/groot/api/save", json={"rows": ticked}).json()

    assert result["message"] == "Saved 2 deadlines to your list."
    assert [(d["title"], d["due_date"]) for d in json.loads(deadlines_file.read_text())] == [
        ("33130 Skills Test 1", "2026-08-07 23:59"),
        ("33130 Essay", "2026-08-14 17:00"),
    ]


def test_save_with_no_rows(client, deadlines_file):
    result = client.post("/groot/api/save", json={"rows": []}).json()
    assert result == {"status": "success", "message": "No rows were ticked, so nothing was saved.", "results": []}
    assert not deadlines_file.exists()


@pytest.mark.parametrize("data", [{}, {"rows": "Essay"}, {"rows": ["Essay"]}, {"rows": [{"title": "Essay", "due_date": "friday"}]}])
def test_save_refuses_rows_of_the_wrong_shape(client, deadlines_file, data):
    response = client.post("/groot/api/save", json=data)

    assert (response.status_code, response.json()["message"]) == (400, 'Each row to save needs a "title", a "due_date" and a "subject".')
    assert not deadlines_file.exists()


# ---------- Gemini is only used by Preview ----------


def test_no_endpoint_uses_gemini_unless_preview_is_used(client, reader, no_gemini):
    for path in ["/groot", "/groot/import", *(f"/groot/static/{name}" for name in web_app.STATIC_FILES)]:
        assert client.get(path).status_code == 200
    changes = [
        ("/groot/api/add", {"title": "Quiz", "due_date": "friday", "subject": ""}),
        ("/groot/api/done", {"title": "Quiz"}),
        ("/groot/api/export", {}),
        ("/groot/api/delete", {"title": "Quiz"}),
        ("/groot/api/save", {"rows": [{"title": "Essay", "due_date": "friday", "subject": ""}]}),
    ]
    for path, data in changes:
        assert client.post(path, json=data).status_code == 200
    assert reader == []

    preview(client, ("maths.pdf", pdf("maths")), ("foundation.pdf", pdf("foundation")))
    assert reader == [pdf("maths"), pdf("foundation")]  # one request for each outline, and only now
