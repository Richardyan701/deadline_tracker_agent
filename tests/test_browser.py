"""Tests for Groot's website: web/browser.py, the build, and the page's script and settings.

The website runs web/browser.py inside the student's own browser (see
website/app.js), so these tests run the same file in ordinary Python.
No API key and no internet needed. The clock is frozen at Thursday 5 Nov 2026.
"""

import ast
import json
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deadline_agent import tools
from web import app as web_app
from web import browser, pages

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
NOW = datetime(2026, 11, 5, 10, 0)  # Thursday 5 Nov 2026, 10:00 AM


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary folder and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setenv("DEADLINES_ICS_FILE", str(tmp_path / "deadlines.ics"))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def ask(action, data=None):
    """Send one request the way app.js does: JSON text in, JSON text out."""
    return json.loads(browser.handle_json(action, json.dumps(data or {})))


def titles():
    return [deadline["title"] for deadline in tools.list_deadlines()["deadlines"]]


# ---------- the page ----------


def test_the_website_page_says_where_the_deadlines_are_kept():
    page = browser.home_html()
    assert pages.WEBSITE_NOTE in page
    assert '<button type="button" id="backup-button" class="secondary">Download backup</button>' in page
    assert 'id="restore-input"' in page
    assert '<button type="button" id="sample-button" class="secondary">Try a sample semester</button>' in page
    assert '<button type="button" id="remove-examples-button" class="secondary">Remove examples</button>' in page
    assert "<p>Private: your deadlines are saved only in this browser.</p>" in page
    assert '<select id="home-session"' in page and '<form id="add-form">' in page


def test_the_website_page_has_no_links_to_pages_it_does_not_have():
    # The website is only the home page, at github.io/deadline_tracker_agent/, so a link like
    # "/groot/import" would lead nowhere. Every link must go to another website.
    page = browser.home_html()
    assert "Import from outlines" not in page and "Chat with Groot" not in page
    for link in re.findall(r'href="([^"]*)"', page):
        assert link.startswith("https://"), link


def test_the_empty_list_suggests_the_examples_on_the_website_and_the_import_on_the_laptop():
    assert 'try "Add example deadlines" at the bottom of this page' in browser.home_html()
    laptop = pages.home_page(tools.get_reminders(), [], NOW, [])
    assert '<a href="/groot/import">import them from your subject outlines</a>' in laptop
    assert "backup-button" not in laptop and pages.WEBSITE_NOTE not in laptop


# ---------- every request, the same as on the laptop ----------


def test_add_done_edit_mark_and_delete():
    assert ask("add", {"title": "Quiz 1", "due_date": "friday 5pm", "subject": "Maths"})["message"] == (
        "Saved 'Quiz 1', due Friday 6 Nov 2026, 5:00 PM."
    )
    assert ask("edit", {"title": "Quiz 1", "new_title": "Quiz A", "due_date": "", "subject": ""})["status"] == "success"
    assert tools.list_deadlines()["deadlines"][0].get("subject", "") == ""  # an empty subject removes it, as in app.py
    assert ask("mark", {"title": "Quiz A", "mark_percent": 80, "weight_percent": 10})["status"] == "success"
    assert ask("done", {"title": "Quiz A"})["message"] == "Marked 'Quiz A' as done."
    assert ask("delete", {"title": "Quiz A"})["message"] == "Deleted 'Quiz A'."
    assert titles() == []


def test_week_numbers_work_on_the_website():
    assert ask("session", {"session": "NUS_AY2627_S2"})["status"] == "success"
    result = ask("add", {"title": "Lab", "due_date": "friday week 7 5pm", "subject": ""})
    assert result["deadline"]["due_date"] == "2027-03-05 17:00"
    assert "Today is" not in browser.home_html()  # 5 Nov 2026 is before NUS's week 1
    assert "has not started yet. Week 1 starts on Monday 11 Jan 2027." in browser.home_html()


def test_export_hands_back_the_calendar_text_with_its_line_endings():
    ask("add", {"title": "Quiz 1", "due_date": "friday 5pm", "subject": ""})
    result = ask("export")
    assert result["status"] == "success" and result["exported"] == 1
    assert result["calendar"].startswith("BEGIN:VCALENDAR\r\n")
    assert "\n" not in result["calendar"].replace("\r\n", "")  # every line ends in \r\n, as calendar files need


def test_export_with_nothing_to_export_has_no_calendar():
    result = ask("export")
    assert result["exported"] == 0 and "calendar" not in result


def test_unknown_or_broken_requests_are_refused():
    assert ask("format_my_laptop") == {"status": "error", "message": "Groot does not know that request."}
    assert json.loads(browser.handle_json("add", "not json"))["message"] == "Groot did not understand that request."
    assert json.loads(browser.handle_json("add", "[1, 2]"))["message"] == "Groot did not understand that request."
    assert titles() == []


# ---------- backups ----------


def test_backup_then_restore_brings_everything_back():
    ask("session", {"session": "AUT2027"})
    ask("add", {"title": "Quiz 1", "due_date": "friday 5pm", "subject": "Maths"})
    ask("add", {"title": "Essay", "due_date": "in 10 days", "subject": ""})
    backup = ask("backup")
    assert backup["message"] == "Backup ready: 2 deadlines."
    saved = json.loads(backup["backup"])
    assert saved["format"] == browser.BACKUP_FORMAT and saved["session"] == "AUT2027" and len(saved["deadlines"]) == 2

    ask("delete", {"title": "Quiz 1"})
    ask("session", {"session": ""})
    result = ask("restore", {"backup": backup["backup"]})
    assert result["message"] == "Restored 2 deadlines from your backup. Your university session was restored too."
    assert sorted(titles()) == ["Essay", "Quiz 1"]
    assert tools._chosen_session() == "AUT2027"


def test_restore_accepts_the_laptop_versions_deadlines_file(deadlines_file):
    ask("add", {"title": "Quiz 1", "due_date": "friday 5pm", "subject": ""})
    laptop_file = deadlines_file.read_text(encoding="utf-8")
    ask("delete", {"title": "Quiz 1"})
    assert ask("restore", {"backup": laptop_file})["message"] == "Restored 1 deadline from your backup."
    assert titles() == ["Quiz 1"]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        '{"format": "groot-backup-1"}',
        '{"format": "groot-backup-1", "deadlines": [{"title": "No date"}]}',
        '{"format": "someone-else", "deadlines": []}',
        '[{"title": "Quiz", "due_date": "not a date", "subject": "", "done": false}]',
        "42",
        None,
    ],
)
def test_restore_refuses_anything_else_and_changes_nothing(text):
    ask("add", {"title": "Keep me", "due_date": "friday 5pm", "subject": ""})
    result = ask("restore", {"backup": text})
    assert result == {"status": "error", "message": "That file is not a Groot backup, so nothing was changed."}
    assert titles() == ["Keep me"]


def test_restore_ignores_a_session_groot_does_not_know():
    backup = json.dumps({"format": browser.BACKUP_FORMAT, "deadlines": [], "session": "GONE_2019"})
    assert ask("restore", {"backup": backup})["message"] == "Restored 0 deadlines from your backup."
    assert tools._chosen_session() is None


# ---------- the sample semester ----------

# UTS Autumn 2027, worked out by hand: week 2 starts 22 Feb, week 3 1 Mar, week 4 8 Mar, week 5 15 Mar,
# week 7 29 Mar, week 8 5 Apr, StuVac 12 Apr, week 9 19 Apr, week 10 26 Apr
SAMPLE_IN_AUT2027 = {
    "Example: Quiz 1": "2027-02-26 17:00",
    "Example: Annotated bibliography": "2027-03-07 23:59",
    "Example: Lab report": "2027-03-10 09:00",
    "Example: Reflective journal": "2027-03-21 23:59",
    "Example: Case study": "2027-04-02 17:00",
    "Example: Literature review": "2027-04-11 23:59",
    "Example: Group presentation": "2027-04-19 10:00",
    "Example: Essay": "2027-04-20 23:59",
    "Example: Report": "2027-04-30 17:00",
}


def test_the_sample_semester_needs_a_university_first():
    assert ask("sample") == {"status": "error", "message": browser.CHOOSE_FIRST}
    assert titles() == []


def test_the_sample_semester_fills_a_semester_that_has_not_started():
    ask("session", {"session": "AUT2027"})
    result = ask("sample")
    assert result == {
        "status": "success",
        "message": 'Added 9 made-up deadlines for UTS Autumn 2027. "Remove examples" takes them out again.',
        "session": "AUT2027",
    }
    saved = {deadline["title"]: deadline["due_date"] for deadline in tools.list_deadlines()["deadlines"]}
    assert saved == SAMPLE_IN_AUT2027
    # Two deadlines within 48 hours in week 9 show the clash warning once week 9 is near (Sunday 18 Apr 2027)
    clashes = tools._clashes(now=datetime(2027, 4, 18, 9, 0))
    assert [[d["title"] for d in clash["deadlines"]] for clash in clashes if clash["type"] == "close_together"] == [
        ["Example: Group presentation", "Example: Essay"]
    ]


def test_a_semester_that_has_started_moves_the_sample_to_the_next_one():
    # On 5 Nov 2026 UNSW Term 3 2026 is nearly over, so the sample goes in Term 1 2027 (week 2 starts 22 Feb)
    ask("session", {"session": "UNSW_T3_2026"})
    result = ask("sample")
    assert result["message"] == (
        'Added 9 made-up deadlines for UNSW Term 1 2027. Week numbers now count in UNSW Term 1 2027. '
        '"Remove examples" takes them out again.'
    )
    assert tools._chosen_session() == "UNSW_T1_2027"
    assert tools.list_deadlines()["deadlines"][0]["due_date"] == "2027-02-26 17:00"


def test_no_later_semester(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 9, 1, 10, 0))
    ask("session", {"session": "NUS_AY2728_S1"})  # started on 9 Aug 2027, and it is the last NUS one here
    assert ask("sample") == {"status": "error", "message": "Groot doesn't have a later NUS semester yet."}


def test_the_sample_is_added_once_and_removed_without_touching_real_deadlines():
    ask("session", {"session": "AUT2027"})
    ask("add", {"title": "My real essay", "due_date": "friday 5pm", "subject": ""})
    ask("sample")
    assert ask("sample") == {"status": "error", "message": "The sample semester is already in your list."}
    assert ask("removeexamples") == {"status": "success", "message": "Removed 9 made-up deadlines."}
    assert titles() == ["My real essay"]
    assert ask("removeexamples") == {"status": "error", "message": "There are no made-up deadlines to remove."}


def test_backups_keep_the_reminder_times():
    ask("reminders", {"reminders": ["1d", "5h", "30m"]})
    backup = ask("backup")["backup"]
    assert json.loads(backup)["reminders"] == ["1d", "5h", "30m"]
    ask("reminders", {"reminders": []})
    ask("restore", {"backup": backup})
    assert tools.chosen_reminders() == ["1d", "5h", "30m"]


def test_an_older_backup_without_reminder_times_keeps_the_current_ones():
    ask("reminders", {"reminders": ["2d"]})
    older = json.dumps({"format": browser.BACKUP_FORMAT, "deadlines": [], "session": ""})
    assert ask("restore", {"backup": older})["status"] == "success"
    assert tools.chosen_reminders() == ["2d"]


def test_paste_works_on_the_website():
    checked = ask("paste", {"text": "Quiz 1, friday 5pm, Statistics"})
    assert checked["status"] == "success" and titles() == []  # checking saves nothing
    added = ask("paste", {"text": "Quiz 1, friday 5pm, Statistics", "save": True})
    assert added["message"] == "Added 1 deadline." and titles() == ["Quiz 1"]


# ---------- the website only needs what a browser has ----------

# Run in a fresh Python that refuses to import anything outside the standard library, apart from
# Groot's own code, tzdata (app.js loads it into the browser) and the stand-in for python-dotenv.
ONLY_THE_STANDARD_LIBRARY = textwrap.dedent(
    """
    import importlib.abc, importlib.machinery, json, os, sys, sysconfig, tempfile, types
    ALLOWED = set(sys.stdlib_module_names) | {"deadline_agent", "web", "dotenv", "tzdata"}
    # A few standard library files have names that depend on the machine, like Linux's
    # _sysconfigdata__linux_x86_64-linux-gnu, so they are not in sys.stdlib_module_names.
    # Those are allowed when they really are in Python's own standard library folder.
    STDLIB = {os.path.normcase(sysconfig.get_paths()[key]) for key in ("stdlib", "platstdlib")}

    def in_the_standard_library(name, path):
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        origin = os.path.normcase(getattr(spec, "origin", None) or "")
        return bool(origin) and "site-packages" not in origin and any(origin.startswith(folder) for folder in STDLIB)

    class Refuse(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name.split(".")[0] not in ALLOWED and not in_the_standard_library(name, path):
                raise ImportError(f"the website cannot import {name}")

    sys.meta_path.insert(0, Refuse())
    dotenv = types.ModuleType("dotenv")
    dotenv.dotenv_values = lambda *args, **kwargs: {}
    sys.modules["dotenv"] = dotenv
    folder = tempfile.mkdtemp()
    os.environ["DEADLINES_FILE"] = os.path.join(folder, "deadlines.json")
    os.environ["DEADLINES_ICS_FILE"] = os.path.join(folder, "deadlines.ics")
    os.environ["GROOT_COUNTRY"] = "SG"

    from datetime import datetime
    from deadline_agent import tools
    from web import browser
    tools._now = lambda: datetime(2026, 11, 5, 10, 0)  # the same day every time
    browser.home_html()
    for action, data in [
        ("session", {"session": "NUS_AY2627_S2"}), ("sample", {}), ("removeexamples", {}),
        ("reminders", {"reminders": ["1d", "30m"]}),
        ("paste", {"text": "Quiz, friday 5pm"}), ("paste", {"text": "Quiz, friday 5pm", "save": True}),
        ("add", {"title": "Lab", "due_date": "friday week 7 5pm", "subject": ""}),
        ("edit", {"title": "Lab", "new_title": "Lab 1", "due_date": "", "subject": ""}),
        ("mark", {"title": "Lab 1", "mark_percent": 70, "weight_percent": 20}), ("done", {"title": "Lab 1"}),
        ("export", {}), ("backup", {}), ("delete", {"title": "Lab 1"}),
    ]:
        assert json.loads(browser.handle_json(action, json.dumps(data)))["status"] == "success", action
    browser.home_html()
    loaded = sorted(
        os.path.relpath(module.__file__, os.getcwd()).replace(os.sep, "/")
        for name, module in sys.modules.items()
        if name.split(".")[0] in ("deadline_agent", "web") and getattr(module, "__file__", None)
    )
    print(json.dumps(loaded))
    """
)


def test_the_website_code_needs_only_the_standard_library():
    finished = subprocess.run(
        [sys.executable, "-c", ONLY_THE_STANDARD_LIBRARY], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert finished.returncode == 0, finished.stderr[-2000:]
    loaded = json.loads(finished.stdout.strip().splitlines()[-1])
    # Every Groot file the website used is one build.py copies, and every copied file was used
    assert set(loaded) == set(browser.PY_FILES)


# ---------- the build ----------


def build(tmp_path):
    sys.path.insert(0, str(WEBSITE))
    try:
        import build as website_build
    finally:
        sys.path.remove(str(WEBSITE))
    out = tmp_path / "site"
    website_build.build(out)
    return out


def test_the_build_copies_only_the_listed_files(tmp_path):
    out = build(tmp_path)
    built = sorted(str(path.relative_to(out)).replace("\\", "/") for path in out.rglob("*") if path.is_file())
    expected = sorted(
        ["index.html", "app.js", "manifest.webmanifest", "py-files.json"]
        + [f"icons/{name}" for name in ["icon-32.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"]]
        + [f"static/{name}" for name in ["home.js", "common.js", "groot.css"]]
        + [f"py/{path}" for path in browser.PY_FILES]
    )
    assert built == expected  # so a .env file or deadlines.json can never be published
    assert json.loads((out / "py-files.json").read_text(encoding="utf-8")) == browser.PY_FILES
    assert (out / "py" / "web" / "browser.py").read_bytes() == (ROOT / "web" / "browser.py").read_bytes()


def test_the_build_reads_the_file_list_without_running_browser_py():
    tree = ast.parse((ROOT / "web" / "browser.py").read_text(encoding="utf-8"))
    listed = next(
        ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "PY_FILES"
    )
    assert listed == browser.PY_FILES


# ---------- the page, its script and its settings ----------


def test_the_page_only_runs_scripts_from_itself_and_pyodide():
    page = (WEBSITE / "index.html").read_text(encoding="utf-8")
    policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page)[1]
    assert "default-src 'none'" in policy
    assert "script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval';" in policy
    assert "connect-src 'self' https://cdn.jsdelivr.net;" in policy
    assert "'unsafe-inline'" not in policy and "'unsafe-eval'" not in policy.replace("'wasm-unsafe-eval'", "")
    assert "<script>" not in page  # no inline scripts, which the policy would block anyway


def test_pyodide_is_pinned_to_one_exact_version():
    script = (WEBSITE / "app.js").read_text(encoding="utf-8")
    addresses = re.findall(r"https://cdn\.jsdelivr\.net/pyodide/[^\"']+", script)
    assert addresses == ["https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs"]


def test_the_website_redraws_the_same_parts_as_home_js():
    script = (WEBSITE / "app.js").read_text(encoding="utf-8")
    home = (ROOT / "web" / "static" / "home.js").read_text(encoding="utf-8")
    redrawn = json.loads(re.search(r"export const REDRAWN = (\[[^\]]*\]);", script)[1])
    assert f"for (const id of {json.dumps(redrawn)})" in home


def test_every_request_that_changes_something_is_saved():
    script = (WEBSITE / "app.js").read_text(encoding="utf-8")
    listed = re.search(r"const CHANGES = new Set\((\[[^\]]*\])\);", script)[1]
    changes = set(re.findall(r'"([a-z]+)"', listed))
    assert changes == {
        "add", "done", "delete", "edit", "mark", "session", "reminders", "paste", "export", "restore", "sample", "removeexamples",
    }
    for action in changes | {"backup"}:
        assert ask(action)["message"] != "Groot does not know that request.", action


def test_the_app_manifest_and_its_icons():
    manifest = json.loads((WEBSITE / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Agent Groot" and manifest["display"] == "standalone"
    assert manifest["start_url"] == "./" and manifest["scope"] == "./"  # the site lives in a folder on github.io
    for icon in manifest["icons"]:
        size = int(icon["sizes"].split("x")[0])
        data = (WEBSITE / icon["src"]).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert int.from_bytes(data[16:20], "big") == size and int.from_bytes(data[20:24], "big") == size


def test_the_laptop_version_shows_the_tab_icon():
    app = FastAPI()
    web_app.add_groot(app)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    assert '<link rel="icon" href="/groot/static/icon-32.png" type="image/png">' in client.get("/groot").text
    icon = client.get("/groot/static/icon-32.png")
    assert icon.status_code == 200 and icon.headers["content-type"] == "image/png"
    assert icon.content == (WEBSITE / "icons" / "icon-32.png").read_bytes()
