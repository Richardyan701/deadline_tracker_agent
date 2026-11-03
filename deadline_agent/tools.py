"""Deadline tools for Agent Groot.

Each public function here is given to the agent as a tool. Google ADK reads
the function name, type hints and docstring to tell the model what the tool
does, so keep the docstrings clear.

Deadlines are saved in a JSON file, so they survive a restart. The file is
read at the start of every tool call and written after every change.

Due dates are always saved as "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" in Sydney
time. Students can type friendlier things like "next friday 5pm", and the
code below (not the AI model) turns those words into that saved form.
"""

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# The four things we store for every deadline.
REQUIRED_KEYS = {"title", "due_date", "subject", "done"}

# The student studies at UTS, so every date and time is Sydney time.
SYDNEY = ZoneInfo("Australia/Sydney")

# The two saved forms, for example "2026-11-05" and "2026-11-05 14:30".
ISO_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
ISO_DATE_TIME = ISO_DATE + r" [0-9]{2}:[0-9]{2}"

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Every spelling we understand, mapped to a number.
# Weekdays: "fri" -> 4 (Monday is 0). Months: "nov" -> 11.
WEEKDAYS = {name: i for i, name in enumerate(WEEKDAY_NAMES)}
WEEKDAYS |= {name[:3]: i for i, name in enumerate(WEEKDAY_NAMES)}
WEEKDAYS |= {"tues": 1, "thur": 3, "thurs": 3}
MONTHS = {name: i + 1 for i, name in enumerate(MONTH_NAMES)}
MONTHS |= {name[:3]: i + 1 for i, name in enumerate(MONTH_NAMES)}
MONTHS |= {"sept": 9}

# Little words students add that do not change the date, as in "due on friday at 5pm".
FILLER_WORDS = {"due", "by", "on", "at"}

# Added to the end of every date error so the student knows what to type.
DATE_EXAMPLES = "Try something like 'next friday 5pm', 'in 3 days' or '20 nov'."


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
    """The current time in Sydney. Tests replace this so they do not depend on today's date.

    The timezone is removed afterwards, so it can be compared with the saved
    due dates, which are plain Sydney times with no timezone attached.
    """
    return datetime.now(SYDNEY).replace(tzinfo=None)


def _parse_due_date(text) -> datetime:
    """Turn 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM' into a datetime.

    A date with no time counts as due at the end of that day (23:59).
    Raises ValueError for anything else, including dates that do not exist
    such as 2026-02-30.
    """
    if not isinstance(text, str):
        raise ValueError("due date must be text")
    text = text.strip()
    if re.fullmatch(ISO_DATE, text):
        # No time given, so use the end of the day
        return datetime.strptime(text + " 23:59", "%Y-%m-%d %H:%M")
    if re.fullmatch(ISO_DATE_TIME, text):
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    raise ValueError("wrong date format")


def _friendly_day(moment: datetime) -> str:
    """For example 'Friday 20 Nov 2026'."""
    weekday = WEEKDAY_NAMES[moment.weekday()].title()
    month = MONTH_NAMES[moment.month - 1][:3].title()
    return f"{weekday} {moment.day} {month} {moment.year}"


def _friendly(moment: datetime) -> str:
    """For example 'Friday 20 Nov 2026, 5:00 PM'."""
    hour = moment.hour % 12 or 12  # 0 becomes 12 AM, 13 becomes 1 PM
    am_pm = "AM" if moment.hour < 12 else "PM"
    return f"{_friendly_day(moment)}, {hour}:{moment.minute:02d} {am_pm}"


# ---------- understanding the student's date words ----------
#
# The AI model does not know today's date, so it is bad at working out
# things like "next friday". These functions do it with plain rules instead.
# They raise ValueError with a message that is safe to show the student.


def _number(word: str) -> int:
    """'3' -> 3, and 'a' or 'an' -> 1 (as in 'in a week')."""
    return 1 if word in ("a", "an") else int(word)


def _cut(text: str, match) -> str:
    """The text with the matched part removed."""
    return text[: match.start()] + " " + text[match.end():]


def _split_time(text: str):
    """Find a time like '5pm', '5:30 pm', '17:00', 'noon' or 'midnight' in the text.

    Returns (hour, minute) or None, and the rest of the text without the time.
    """
    # 12 hour time with am/pm: "5pm", "5 pm", "5:30pm"
    match = re.search(r"\b([0-9]{1,2})(?::([0-9]{2}))? ?(am|pm)\b", text)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError(f"'{match[0]}' is not a real time. {DATE_EXAMPLES}")
        if match[3] == "am":
            hour = 0 if hour == 12 else hour  # 12am is the start of the day
        else:
            hour = 12 if hour == 12 else hour + 12  # 12pm is noon
        return (hour, minute), _cut(text, match)

    # 24 hour time: "17:00" or "09:30"
    match = re.search(r"\b([0-9]{1,2}):([0-9]{2})\b", text)
    if match:
        if len(match[1]) == 1:
            # "5:30" could be morning or evening, so ask instead of guessing
            raise ValueError(
                f"Is '{match[0]}' in the morning or evening? Add am or pm (like 5:30pm) "
                "or use 24 hour time (like 17:30)."
            )
        hour, minute = int(match[1]), int(match[2])
        if hour > 23 or minute > 59:
            raise ValueError(f"'{match[0]}' is not a real time. {DATE_EXAMPLES}")
        return (hour, minute), _cut(text, match)

    # Words. "midnight" means the end of that day, like a date with no time.
    match = re.search(r"\b(noon|midday|midnight)\b", text)
    if match:
        return ((23, 59) if match[1] == "midnight" else (12, 0)), _cut(text, match)

    return None, text


def _real_date(year: int, month: int, day: int) -> date:
    """Make a date, or explain that it does not exist (like 30 Feb)."""
    try:
        return date(year, month, day)
    except ValueError:
        if 1 <= month <= 12:
            shown = f"{day} {MONTH_NAMES[month - 1][:3].title()} {year}"
        else:
            shown = f"{day}/{month}/{year}"
        raise ValueError(f"{shown} doesn't exist, so please check the day and month. {DATE_EXAMPLES}") from None


def _read_day(text: str, today: date):
    """Turn the date part of the words (with any time already removed) into a date.

    Returns None if the words are not a date we know.
    """
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)

    # Up to 3 digits, so a silly number cannot go past the year 9999
    match = re.fullmatch(r"in ([0-9]{1,3}|an?) (day|days|week|weeks)", text)
    if match:
        days = _number(match[1]) * (7 if match[2].startswith("week") else 1)
        return today + timedelta(days=days)

    # Weeks run Monday to Sunday.
    # "friday" is the next Friday after today (never today itself).
    # "next friday" is the Friday in next week.
    match = re.fullmatch(r"(next )?([a-z]+)", text)
    if match and match[2] in WEEKDAYS:
        target = WEEKDAYS[match[2]]
        if match[1]:
            monday_next_week = today + timedelta(days=7 - today.weekday())
            return monday_next_week + timedelta(days=target)
        days_ahead = (target - today.weekday() - 1) % 7 + 1  # always 1 to 7
        return today + timedelta(days=days_ahead)

    # "20 nov", "20th november", "20 nov 2026"
    match = re.fullmatch(r"([0-9]{1,2})(?:st|nd|rd|th)? ([a-z]+)(?: ([0-9]{4}))?", text)
    if match and match[2] in MONTHS:
        year = int(match[3]) if match[3] else today.year
        return _real_date(year, MONTHS[match[2]], int(match[1]))

    # "20/11" or "20/11/2026". Day comes first, as in Australia.
    match = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})(?:/([0-9]{4}))?", text)
    if match:
        year = int(match[3]) if match[3] else today.year
        return _real_date(year, int(match[2]), int(match[1]))

    return None


def _read_words(text: str, now: datetime):
    """Turn friendly words like 'next friday 5pm' into the saved form.

    Returns None if the words are not a date we know.
    """
    words = [word for word in text.lower().replace(",", " ").split() if word not in FILLER_WORDS]
    text = " ".join(words)

    # "in 2 hours" is an exact moment from now, so it keeps its minutes
    match = re.fullmatch(r"in ([0-9]{1,3}|an?) (hour|hours)", text)
    if match:
        return (now + timedelta(hours=_number(match[1]))).strftime("%Y-%m-%d %H:%M")

    # "end of the week" is this Sunday, "end of next week" is next Sunday.
    # Saved with no time, so it lasts until 23:59 that Sunday.
    match = re.fullmatch(r"end of (?:the |this )?(next )?week", text)
    if match:
        sunday = now.date() + timedelta(days=6 - now.weekday() + (7 if match[1] else 0))
        return sunday.isoformat()

    time, date_text = _split_time(text)
    date_text = " ".join(date_text.split())
    if not date_text and time is None:
        return None  # nothing was typed
    # Just a time like "5pm" means today
    day = _read_day(date_text, now.date()) if date_text else now.date()
    if day is None:
        return None
    if time is None:
        return day.isoformat()
    return f"{day.isoformat()} {time[0]:02d}:{time[1]:02d}"


def _understand_due_date(phrase: str, now: datetime) -> str:
    """Turn what the student typed into "YYYY-MM-DD" or "YYYY-MM-DD HH:MM".

    Raises ValueError with a friendly message if the words are unclear, the
    date does not exist, or the date is already in the past.
    """
    text = phrase.strip()
    if re.fullmatch(ISO_DATE, text) or re.fullmatch(ISO_DATE_TIME, text):
        # Already in the saved form, so keep it exactly as typed (like task 1)
        saved = text
        try:
            due = _parse_due_date(saved)
        except ValueError:
            raise ValueError(f"'{text}' is not a real date or time. {DATE_EXAMPLES}") from None
    else:
        saved = _read_words(text, now)
        if saved is None:
            raise ValueError(f"I couldn't work out a date from '{text}'. {DATE_EXAMPLES}")
        due = _parse_due_date(saved)

    if due < now:
        raise ValueError(
            f"'{text}' would be {_friendly(due)}, which is already in the past. "
            "Please check the date, and add the year if you meant next year (like '20 jan 2027')."
        )
    return saved


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
        due_date: When it is due, in the student's own words exactly as they
            typed them. Do not convert it yourself, this tool works out the
            date using today's date in Sydney. Understood forms:
            "today", "tomorrow", "in 3 days", "in 2 weeks", "in 4 hours",
            "friday" (the next Friday after today), "next friday" (the Friday
            of next week), "20 nov", "20 november 2026", "20/11",
            "20/11/2026" (day first), "end of the week", "end of next week",
            or "2026-11-20" and "2026-11-20 14:30".
            A time can be added to any of the date words, for example
            "next friday 5pm", "tomorrow 5:30pm", "20 nov 17:00",
            "friday noon" or "friday midnight". With no time, it is due at
            the end of that day (11:59 PM).
        subject: Optional university subject, for example "Machine Learning".

    Returns:
        A dict with "status" ("success" or "error") and a "message". On
        success it also has the saved "deadline". If the date is unclear,
        does not exist or is in the past, the message explains why, so ask
        the student to check it.
    """
    title = title.strip()
    if not title:
        return {"status": "error", "message": "A deadline needs a title."}

    try:
        saved_date = _understand_due_date(due_date, _now())
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    deadlines = _load_deadlines()
    if _find(deadlines, title) is not None:
        return {
            "status": "error",
            "message": f"You already have a deadline called '{title}'. Pick a different title.",
        }

    new_deadline = {
        "title": title,
        "due_date": saved_date,
        "subject": subject.strip(),
        "done": False,
    }
    deadlines.append(new_deadline)
    _save_deadlines(deadlines)
    return {
        "status": "success",
        # Show the date in full so the student can spot a mistake
        "message": f"Saved '{title}', due {_friendly(_parse_due_date(saved_date))}.",
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
