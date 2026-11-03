"""Deadline tools for Agent Groot.

Each public function here is given to the agent as a tool. Google ADK reads
the function name, type hints and docstring to tell the model what the tool
does, so keep the docstrings clear.

Deadlines are saved in a JSON file, so they survive a restart. The file is
read at the start of every tool call and written after every change.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

# The four things we store for every deadline.
REQUIRED_KEYS = {"title", "due_date", "subject", "done"}


# ---------- helpers (not tools, the model never sees these) ----------


def _data_file() -> Path:
    """Where the deadlines are saved.

    Uses the DEADLINES_FILE environment variable if it is set (the tests do
    this). Otherwise it is deadlines.json next to the deadline_agent folder.
    """
    custom_path = os.environ.get("DEADLINES_FILE")
    if custom_path:
        return Path(custom_path)
    return Path(__file__).resolve().parent.parent / "deadlines.json"


def _now() -> datetime:
    """The current time. Tests replace this so they do not depend on today's date."""
    return datetime.now()


def _parse_due_date(text) -> datetime:
    """Turn 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM' into a datetime.

    A date with no time counts as due at the end of that day (23:59).
    Raises ValueError for anything else, including dates that do not exist
    such as 2026-02-30.
    """
    if not isinstance(text, str):
        raise ValueError("due date must be text")
    text = text.strip()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        # No time given, so use the end of the day
        return datetime.strptime(text + " 23:59", "%Y-%m-%d %H:%M")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}", text):
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    raise ValueError("wrong date format")


def _looks_valid(deadlines) -> bool:
    """True if the loaded data is a list of well formed deadlines."""
    if not isinstance(deadlines, list):
        return False
    for deadline in deadlines:
        if not isinstance(deadline, dict) or not REQUIRED_KEYS <= deadline.keys():
            return False
        if not isinstance(deadline["title"], str) or not isinstance(deadline["subject"], str):
            return False
        if not isinstance(deadline["done"], bool):
            return False
        try:
            _parse_due_date(deadline["due_date"])
        except ValueError:
            return False
    return True


def _load_deadlines() -> list:
    """Read all deadlines from the file.

    A missing or corrupted file is treated as "no deadlines yet" instead of
    crashing. (The next change will then write a fresh, valid file.)
    """
    path = _data_file()
    if not path.exists():
        return []
    try:
        deadlines = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:  # bad JSON or bad text encoding
        return []
    if not _looks_valid(deadlines):
        return []
    return deadlines


def _save_deadlines(deadlines: list) -> None:
    """Write all deadlines to the file."""
    _data_file().write_text(json.dumps(deadlines, indent=2), encoding="utf-8")


def _find(deadlines: list, title: str):
    """Return the deadline with this title (ignoring upper/lower case), or None."""
    wanted = title.strip().casefold()
    for deadline in deadlines:
        if deadline["title"].casefold() == wanted:
            return deadline
    return None


def _soonest_first(deadlines: list) -> list:
    """Return a new list sorted by due date, soonest first."""
    return sorted(deadlines, key=lambda d: _parse_due_date(d["due_date"]))


def _not_found(title: str) -> dict:
    return {
        "status": "error",
        "message": f"I couldn't find a deadline called '{title}'. Check the spelling or ask me to list your deadlines.",
    }


# ---------- the tools ----------


def add_deadline(title: str, due_date: str, subject: str = "") -> dict:
    """Saves a new deadline for the student.

    Args:
        title: Name of the task, for example "Assignment 1". Must be unique
            (upper/lower case is ignored).
        due_date: When it is due. Must be exactly "YYYY-MM-DD" (for example
            "2026-11-05") or "YYYY-MM-DD HH:MM" in 24 hour time (for example
            "2026-11-05 14:30"). No other format is accepted.
        subject: Optional university subject, for example "Machine Learning".

    Returns:
        A dict with "status" ("success" or "error") and a "message". On
        success it also has the saved "deadline".
    """
    title = title.strip()
    if not title:
        return {"status": "error", "message": "A deadline needs a title."}

    try:
        _parse_due_date(due_date)
    except ValueError:
        return {
            "status": "error",
            "message": (
                f"'{due_date}' is not a valid date. Use YYYY-MM-DD (like 2026-11-05) "
                "or YYYY-MM-DD HH:MM (like 2026-11-05 14:30)."
            ),
        }

    deadlines = _load_deadlines()
    if _find(deadlines, title) is not None:
        return {
            "status": "error",
            "message": f"You already have a deadline called '{title}'. Pick a different title.",
        }

    new_deadline = {
        "title": title,
        "due_date": due_date.strip(),
        "subject": subject.strip(),
        "done": False,
    }
    deadlines.append(new_deadline)
    _save_deadlines(deadlines)
    return {
        "status": "success",
        "message": f"Saved '{title}', due {new_deadline['due_date']}.",
        "deadline": new_deadline,
    }


def list_deadlines() -> dict:
    """Lists every saved deadline, soonest first, including finished ones.

    Returns:
        A dict with "status", a "message" and "deadlines", a list where each
        item has "title", "due_date", "subject" and "done" (True if finished).
    """
    deadlines = _soonest_first(_load_deadlines())
    if not deadlines:
        return {"status": "success", "message": "You have no deadlines saved yet.", "deadlines": []}
    return {
        "status": "success",
        "message": f"You have {len(deadlines)} saved deadline(s).",
        "deadlines": deadlines,
    }


def next_deadline() -> dict:
    """Finds the next upcoming deadline that is not finished yet.

    Deadlines that are already done or already past are skipped. A deadline
    with no time is still upcoming until the end of that day.

    Returns:
        A dict with "status", a "message" and "deadline" (the next one, or
        None if nothing is coming up).
    """
    now = _now()
    upcoming = [
        d for d in _load_deadlines()
        if not d["done"] and _parse_due_date(d["due_date"]) >= now
    ]
    if not upcoming:
        return {"status": "success", "message": "You have no upcoming deadlines.", "deadline": None}

    soonest = _soonest_first(upcoming)[0]
    return {
        "status": "success",
        "message": f"Your next deadline is '{soonest['title']}', due {soonest['due_date']}.",
        "deadline": soonest,
    }


def delete_deadline(title: str) -> dict:
    """Permanently deletes a saved deadline.

    Args:
        title: The title of the deadline to delete (upper/lower case is ignored).

    Returns:
        A dict with "status" ("success" or "error") and a "message".
    """
    deadlines = _load_deadlines()
    found = _find(deadlines, title)
    if found is None:
        return _not_found(title)

    deadlines.remove(found)
    _save_deadlines(deadlines)
    return {"status": "success", "message": f"Deleted '{found['title']}'."}


def mark_done(title: str) -> dict:
    """Marks a saved deadline as finished.

    Args:
        title: The title of the deadline that is done (upper/lower case is ignored).

    Returns:
        A dict with "status" ("success" or "error") and a "message".
    """
    deadlines = _load_deadlines()
    found = _find(deadlines, title)
    if found is None:
        return _not_found(title)

    found["done"] = True
    _save_deadlines(deadlines)
    return {"status": "success", "message": f"Marked '{found['title']}' as done."}
