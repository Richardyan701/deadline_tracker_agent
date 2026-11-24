"""Groot's website: the home page and its actions, run inside the student's own browser.

On the laptop, web/app.py answers the home page's requests. On the website
there is no server. site/app.js runs Python in the browser with Pyodide,
loads this file, and hands it each request that home.js makes. So the
website uses exactly the same tools, dates and pages as the laptop version.

The deadlines file lives in the browser's memory, and app.js copies it into
the browser's own storage after every change. Nothing is ever sent anywhere.

Only the Python standard library is used here and in the modules this
imports (PY_FILES), because the browser has nothing else installed.
tests/test_browser.py checks that.
"""

import json

from deadline_agent import tools
from web import pages

# Every Python file the website needs, which site/build.py copies next to the page
PY_FILES = [
    "deadline_agent/__init__.py",
    "deadline_agent/calendars.py",
    "deadline_agent/model_choice.py",
    "deadline_agent/privacy.py",
    "deadline_agent/region.py",
    "deadline_agent/tools.py",
    "web/__init__.py",
    "web/browser.py",
    "web/pages.py",
]

# Marks a file made by Download backup, so Restore can tell it from other JSON files
BACKUP_FORMAT = "groot-backup-1"

# What "Add example deadlines" adds. The dates are words, so they are always in the future.
EXAMPLES = [
    ("Example: Quiz 1", "friday 5pm", "Example subject"),
    ("Example: Essay draft", "in 10 days", "Example subject"),
    ("Example: Group presentation", "in 3 weeks", "Another example subject"),
]


def home_html() -> str:
    """The inside of the website's home page, drawn from the deadlines in this browser."""
    deadlines = tools.list_deadlines()["deadlines"]
    return pages.home_body(tools.get_reminders(), deadlines, tools._now(), tools._all_grade_reports(), website=True)


def handle_json(action: str, body: str) -> str:
    """handle(), with JSON text in and out, which is the easiest way to talk to JavaScript."""
    return json.dumps(handle(action, body))


def handle(action: str, body: str) -> dict:
    """Answer one request from the home page, the same way app.py does on the laptop.

    action is the last part of the address, like "add" for /groot/api/add,
    and body is the JSON text the page sent. Returns a dict with "status" and
    "message". For export it also has "calendar" (the .ics text) when there
    is something to download, and for backup it has "backup" (the file's text).
    """
    try:
        data = json.loads(body or "{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {"status": "error", "message": "Groot did not understand that request."}

    if action == "add":
        return tools.add_deadline(data.get("title"), data.get("due_date"), data.get("subject"))
    if action == "done":
        return tools.mark_done(data.get("title"))
    if action == "delete":
        return tools.delete_deadline(data.get("title"))
    if action == "edit":
        # The form always sends the subject, so an empty one means "remove the subject" (as in app.py)
        subject = data.get("subject")
        return tools.edit_deadline(
            data.get("title"),
            data.get("new_title"),
            data.get("due_date"),
            subject,
            remove_subject=isinstance(subject, str) and not subject.strip(),
        )
    if action == "mark":
        return tools.set_mark(data.get("title"), data.get("mark_percent"), data.get("weight_percent"))
    if action == "session":
        return tools.choose_session(data.get("session"))
    if action == "export":
        return export()
    if action == "backup":
        return backup()
    if action == "restore":
        return restore(data.get("backup"))
    if action == "examples":
        return add_examples()
    return {"status": "error", "message": "Groot does not know that request."}


def export() -> dict:
    """Make the calendar file, and return its text so the page can download it."""
    result = tools.export_calendar()
    if result["status"] == "success" and result["exported"]:
        # read_bytes keeps the \r\n line endings that calendar files need (read_text would change them)
        result["calendar"] = tools._calendar_file().read_bytes().decode("utf-8")
    return result


def backup() -> dict:
    """Everything saved in this browser, as the text of a backup file."""
    with tools._file_lock:
        deadlines = tools._load_deadlines()
    session = tools._chosen_session() or ""
    text = json.dumps({"format": BACKUP_FORMAT, "deadlines": deadlines, "session": session}, indent=2) + "\n"
    return {"status": "success", "message": f"Backup ready: {tools._plural(len(deadlines), 'deadline')}.", "backup": text}


def restore(text) -> dict:
    """Replace the deadlines in this browser with the ones in a backup file's text.

    It also accepts deadlines.json from the laptop version, so a student can
    move their deadlines to the website. Anything else is refused, and then
    nothing changes.
    """
    refused = {"status": "error", "message": "That file is not a Groot backup, so nothing was changed."}
    try:
        saved = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return refused
    if isinstance(saved, list):  # the laptop version's deadlines.json
        deadlines, session = saved, ""
    elif isinstance(saved, dict) and saved.get("format") == BACKUP_FORMAT:
        deadlines, session = saved.get("deadlines"), saved.get("session")
    else:
        return refused
    if not tools._looks_valid(deadlines):
        return refused

    with tools._file_lock:
        try:
            tools._save_deadlines(deadlines)
        except OSError as error:
            return tools._not_saved(error)
    message = f"Restored {tools._plural(len(deadlines), 'deadline')} from your backup."
    if isinstance(session, str) and session and tools.choose_session(session)["status"] == "success":
        message += " Your university session was restored too."
    return {"status": "success", "message": message}


def add_examples() -> dict:
    """Add a few example deadlines, so a new student can try Groot straight away."""
    added = sum(tools.add_deadline(*example)["status"] == "success" for example in EXAMPLES)
    if not added:
        return {"status": "error", "message": "The example deadlines are already in your list."}
    return {
        "status": "success",
        "message": f"Added {tools._plural(added, 'example deadline')}. Delete them whenever you like.",
    }
