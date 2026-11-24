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

from deadline_agent import calendars, paste, tools
from web import pages

# Every Python file the website needs, which site/build.py copies next to the page
PY_FILES = [
    "deadline_agent/__init__.py",
    "deadline_agent/calendars.py",
    "deadline_agent/model_choice.py",
    "deadline_agent/paste.py",
    "deadline_agent/privacy.py",
    "deadline_agent/region.py",
    "deadline_agent/tools.py",
    "web/__init__.py",
    "web/browser.py",
    "web/pages.py",
]

# Marks a file made by Download backup, so Restore can tell it from other JSON files
BACKUP_FORMAT = "groot-backup-1"

# Every made-up deadline starts with this, so "Remove examples" can find them all
EXAMPLE_PREFIX = "Example: "

# What "Try a sample semester" adds: common assessment types, due the way outlines say it.
# The types are from UTS's "Types of assignments" page, Macquarie's assessment types guide and
# NUS's grading policy. Every week is 10 or lower, because UNSW terms have 10 weeks.
# Each is (title, due date in words, subject, weight in percent).
SAMPLE = [
    ("Example: Quiz 1", "friday week 2 5pm", "Statistics", 10),
    ("Example: Annotated bibliography", "sunday week 3 11:59pm", "Academic Writing", 15),
    ("Example: Lab report", "wednesday week 4 9am", "Biology", 20),
    ("Example: Reflective journal", "sunday week 5 11:59pm", "Academic Writing", 10),
    ("Example: Case study", "friday week 7 5pm", "Statistics", 30),
    ("Example: Literature review", "sunday week 8 11:59pm", "Academic Writing", 25),
    ("Example: Group presentation", "monday week 9 10am", "Biology", 25),
    ("Example: Essay", "tuesday week 9 11:59pm", "Academic Writing", 40),
    ("Example: Report", "friday week 10 5pm", "Statistics", 30),
]
CHOOSE_FIRST = 'First choose your university under "Week numbers count in" (in "Add a deadline"), then try again.'


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
    if action == "reminders":
        return tools.choose_reminders(data.get("reminders"))
    if action == "paste":
        return paste.add(data.get("text")) if data.get("save") is True else paste.check(data.get("text"))
    if action == "export":
        return export()
    if action == "backup":
        return backup()
    if action == "restore":
        return restore(data.get("backup"))
    if action == "sample":
        return add_sample()
    if action == "removeexamples":
        return remove_examples()
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
    saved = {"format": BACKUP_FORMAT, "deadlines": deadlines, "session": session, "reminders": tools.chosen_reminders()}
    text = json.dumps(saved, indent=2) + "\n"
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
        deadlines, session, reminders = saved, "", None
    elif isinstance(saved, dict) and saved.get("format") == BACKUP_FORMAT:
        deadlines, session, reminders = saved.get("deadlines"), saved.get("session"), saved.get("reminders")
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
    if reminders is not None:
        tools.choose_reminders(reminders)  # an older backup has none, and a broken list is refused and ignored
    return {"status": "success", "message": message}


def sample_session() -> tuple[str | None, str]:
    """The session the sample semester goes in, and a problem to show when there is none.

    It is the chosen session when it has not started yet. Otherwise it is the
    next session of the same university, because the weeks of a session
    that has started are partly in the past, and Groot refuses past dates.
    """
    chosen = tools._chosen_session()
    if chosen is None:
        return None, CHOOSE_FIRST
    today = tools._now().date()
    info = calendars.session_info(chosen)
    if info["weeks"][0] > today:
        return chosen, ""
    later = sorted(
        (other["weeks"][0], code)
        for code, other in calendars.SESSIONS.items()
        if other["university"] == info["university"] and other["weeks"][0] > today
    )
    if not later:
        return None, f"Groot doesn't have a later {calendars.university_name(chosen)} semester yet."
    return later[0][1], ""


def add_sample() -> dict:
    """Fill the student's next semester with made-up deadlines, so they can see how Groot works.

    It uses week numbers the way outlines do, so the student sees them turn
    into real dates. Two deadlines in week 9 are close together, so a clash
    warning shows when week 9 is near.
    """
    session, problem = sample_session()
    if session is None:
        return {"status": "error", "message": problem}
    switched = session != tools._chosen_session()
    if switched:
        chosen = tools.choose_session(session)
        if chosen["status"] != "success":
            return chosen
    added = sum(tools.add_deadline(*example)["status"] == "success" for example in SAMPLE)
    name = f"{calendars.university_name(session)} {calendars.session_info(session)['name']}"
    if not added:
        return {"status": "error", "message": "The sample semester is already in your list."}
    message = f"Added {tools._plural(added, 'made-up deadline')} for {name}."
    if switched:
        message += f" Week numbers now count in {name}."
    message += ' "Remove examples" takes them out again.'
    return {"status": "success", "message": message, "session": session}


def remove_examples() -> dict:
    """Delete every made-up deadline (their titles start with "Example: ") and nothing else."""
    with tools._file_lock:
        deadlines = tools._load_deadlines()
        kept = [deadline for deadline in deadlines if not deadline["title"].startswith(EXAMPLE_PREFIX)]
        removed = len(deadlines) - len(kept)
        if removed:
            try:
                tools._save_deadlines(kept)
            except OSError as error:
                return tools._not_saved(error)
    if not removed:
        return {"status": "error", "message": "There are no made-up deadlines to remove."}
    return {"status": "success", "message": f"Removed {tools._plural(removed, 'made-up deadline')}."}
