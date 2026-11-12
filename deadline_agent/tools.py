"""Deadline tools for Agent Groot.

Each public function here is given to the agent as a tool. Google ADK reads
the function name, type hints and docstring to tell the model what the tool
does, so keep the docstrings clear.

Deadlines are saved in a JSON file, so they survive a restart. The file is
read at the start of every tool call and written after every change. Each
save writes a complete new file and swaps it in, and a file that cannot be
read is copied to a backup before it is replaced.

Due dates are always saved as "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" in Sydney
time. Students can type friendlier things like "next friday 5pm", and the
code below (not the AI model) turns those words into that saved form.

export_calendar also writes the unfinished deadlines to an iCalendar (.ics)
file, so the student can import them into a calendar app.

Two more things are worked out here in plain Python, never by Gemini:
clashes (deadlines that bunch up close together) and grade_needed (the
average mark still needed for each UTS grade band).
"""

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# The four things we store for every deadline.
REQUIRED_KEYS = {"title", "due_date", "subject", "done"}

# Two optional numbers a deadline can also have, each from 0 to 100.
# Old files do not have them, and a deadline only gets one once it is set.
#   weight_percent: its share of the subject's final mark
#   mark_percent: the student's result for it, once known
PERCENT_KEYS = ("weight_percent", "mark_percent")

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

# Reminders look this many days ahead unless asked otherwise, and never more than MAX_DAYS_AHEAD.
REMINDER_DAYS = 7
MAX_DAYS_AHEAD = 60

# Clash warnings: two deadlines due this close together, or this many in one
# Monday to Sunday week. Only clashes that start within CLASH_DAYS are shown,
# the same 7 days as the reminders.
CLASH_HOURS = 48
BUSY_WEEK_COUNT = 3
CLASH_DAYS = REMINDER_DAYS

# The UTS grade bands, with the final mark each one starts at.
GRADE_BANDS = {
    "pass": ("Pass", 50),
    "credit": ("Credit", 65),
    "distinction": ("Distinction", 75),
    "high distinction": ("High Distinction", 85),
}
# Short names students use for the bands
BAND_NICKNAMES = {"p": "pass", "c": "credit", "cr": "credit", "d": "distinction", "hd": "high distinction"}

# Only one tool call may read or change the file at a time. adk web runs tools
# one after another, but ADK can also run them on several threads at once
# (RunConfig.tool_thread_pool_config), and then two changes made at the same
# moment would undo each other.
_file_lock = threading.Lock()


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


def _utc(moment: datetime) -> datetime:
    """The same Sydney time as a moment in UTC.

    Sydney clocks jump an hour on the two daylight saving nights each year,
    but UTC never jumps. So lengths of time, like "in 3 hours" or "2 hours
    overdue", are worked out in UTC to stay right on those nights.
    """
    return moment.replace(tzinfo=SYDNEY).astimezone(timezone.utc)


def _text(value, name: str) -> str:
    """Tidy up a text argument from the model.

    The model sometimes sends nothing (None), which counts as empty text.
    Runs of spaces, tabs and line breaks become one space, so a title always
    stays on one line. Anything else that is not text, like a number, raises
    ValueError with a message the model can use to try again.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text, but I got {value!r}.")
    return " ".join(value.split())


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
    # 12-hour time with am/pm: "5pm", "5 pm", "5:30pm", or "5.30pm" as Australians often write it
    match = re.search(r"\b([0-9]{1,2})(?:[:.]([0-9]{2}))? ?(am|pm)\b", text)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError(f"'{match[0]}' is not a real time. {DATE_EXAMPLES}")
        if match[3] == "am":
            hour = 0 if hour == 12 else hour  # 12am is the start of the day
        else:
            hour = 12 if hour == 12 else hour + 12  # 12pm is noon
        return (hour, minute), _cut(text, match)

    # 24-hour time: "17:00" or "09:30"
    match = re.search(r"\b([0-9]{1,2}):([0-9]{2})\b", text)
    if match:
        if len(match[1]) == 1:
            # "5:30" could be morning or evening, so ask instead of guessing
            raise ValueError(
                f"Is '{match[0]}' in the morning or evening? Add am or pm (like 5:30pm) "
                "or use 24-hour time (like 17:30)."
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


def _next_date(day: int, month: int, year_text, today: date) -> date:
    """The date for a day and month like "20 nov" or "20/11", with or without a year.

    A year the student typed is always used. With no year, it is the next
    time that date comes round: this year, or next year if this year's has
    already passed. So in November, "20 jan" means 20 January next year.
    """
    if year_text:
        return _real_date(int(year_text), month, day)
    year = today.year
    if (month, day) < (today.month, today.day):
        year += 1  # this year's has already passed
    return _real_date(year, month, day)


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
        return _next_date(int(match[1]), MONTHS[match[2]], match[3], today)

    # "20/11" or "20/11/2026". Day comes first, as in Australia.
    match = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})(?:/([0-9]{4}))?", text)
    if match:
        return _next_date(int(match[1]), int(match[2]), match[3], today)

    return None


def _read_words(text: str, now: datetime):
    """Turn friendly words like 'next friday 5pm' into the saved form.

    Returns None if the words are not a date we know.
    """
    words = [word for word in text.lower().replace(",", " ").split() if word not in FILLER_WORDS]
    text = " ".join(words)

    # "in 2 hours" or "in 30 minutes" is an exact moment from now, so it keeps its minutes.
    # The time is added in UTC, so it is still right on the nights the clocks change.
    match = re.fullmatch(r"in ([0-9]{1,3}|an?) (minute|minutes|hour|hours)", text)
    if match:
        amount = _number(match[1])
        length = timedelta(hours=amount) if match[2].startswith("hour") else timedelta(minutes=amount)
        return (_utc(now) + length).astimezone(SYDNEY).strftime("%Y-%m-%d %H:%M")

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

    Raises ValueError with a friendly message if no date was given, the words
    are unclear, the date does not exist, or the date is already in the past.
    """
    text = phrase.strip()
    if not text:
        raise ValueError(f"Please tell me when it is due. {DATE_EXAMPLES}")
    if re.fullmatch(ISO_DATE, text) or re.fullmatch(ISO_DATE_TIME, text):
        # Already in the saved form, so keep it exactly as typed
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
            "Please check the date and time."
        )
    return saved


def _is_percent(value) -> bool:
    """True if value is a number from 0 to 100. True and False do not count, even though Python treats them as 1 and 0."""
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    return is_number and math.isfinite(value) and 0 <= value <= 100


def _percent(value, name: str):
    """Tidy up a percentage from the model or a web form, like 30, 30.0, "30" or "30%".

    Returns None if nothing was given, otherwise a number from 0 to 100 (a
    whole number like 30.0 becomes 30, so the file shows 30). Raises
    ValueError with a message the model can use for anything else.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    problem = f"{name} must be a number from 0 to 100, but I got {value!r}."  # shows what was really sent
    if isinstance(value, str):
        try:
            value = float(value.strip().removesuffix("%").strip())
        except ValueError:
            raise ValueError(problem) from None
    if not _is_percent(value):
        raise ValueError(problem)
    return int(value) if float(value).is_integer() else value


def _looks_valid(deadlines) -> bool:
    """True if the loaded data is a list of well-formed deadlines."""
    if not isinstance(deadlines, list):
        return False
    for deadline in deadlines:
        if not isinstance(deadline, dict) or not REQUIRED_KEYS <= deadline.keys():
            return False
        if not isinstance(deadline["title"], str) or not isinstance(deadline["subject"], str):
            return False
        if not isinstance(deadline["done"], bool):
            return False
        for key in PERCENT_KEYS:
            # The extra numbers are optional, but must be real percentages when there
            if key in deadline and deadline[key] is not None and not _is_percent(deadline[key]):
                return False
        try:
            _parse_due_date(deadline["due_date"])
        except ValueError:
            return False
    return True


def _read_file(path: Path):
    """The deadlines saved in the file at path.

    Returns [] if there is no file yet, and None if the file is there but
    cannot be read or is not a valid list of deadlines.
    """
    try:
        # "utf-8-sig" also accepts the invisible byte order mark that Windows
        # PowerShell and older Notepad put at the start of UTF-8 files
        deadlines = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):  # no permission, bad text encoding or bad JSON
        return None
    return deadlines if _looks_valid(deadlines) else None


def _load_deadlines() -> list:
    """Read all deadlines from the file.

    A missing file means no deadlines yet. A file that cannot be read or
    understood is treated as empty too, so Groot can always start. That file
    is left exactly as it is, and the next save keeps a copy of it first.
    """
    deadlines = _read_file(_data_file())
    return [] if deadlines is None else deadlines


def _save_deadlines(deadlines: list):
    """Write all deadlines to the file.

    If the file there now cannot be understood, a copy of it is kept first,
    so nothing the student saved is lost. Returns that copy's path, or None
    if no copy was needed. Raises OSError if the file cannot be written.
    """
    path = _data_file()
    backup = _keep_copy(path) if _read_file(path) is None else None
    _replace_file(path, json.dumps(deadlines, indent=2))
    return backup


def _keep_copy(path: Path) -> Path:
    """Copy a file we could not understand to a new file beside it, and return the copy's path.

    The name has the date and time in it, like deadlines.json.corrupt-20261105-100000,
    and a number is added if that name is taken, so an older copy is never overwritten.
    """
    stamp = _now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    number = 1
    while backup.exists():
        number += 1
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{number}")
    shutil.copyfile(path, backup)
    return backup


def _replace_file(path: Path, text: str) -> None:
    """Swap the whole file for new text in one step, so it is never left half-written.

    The text goes into a temporary file in the same folder first, then
    os.replace puts that file in place of the old one in a single step. A
    crash leaves either the old file or the new one, never a mix. If anything
    fails, the old file is untouched and the temporary file is removed.

    newline="" writes the text exactly as given. Without it, Windows changes
    every \\n into \\r\\n, which would turn the \\r\\n line endings of a
    calendar file into \\r\\r\\n.
    """
    temp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, prefix=f"{path.name}.", suffix=".tmp", delete=False
    )
    try:
        with temp:
            temp.write(text)
            temp.flush()
            os.fsync(temp.fileno())  # make sure the text has really reached the disk
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)  # only still there if something failed


def _backup_note(backup) -> str:
    """Extra words for a success message when an unreadable old file was copied first."""
    if backup is None:
        return ""
    return (
        " Your old deadlines file could not be read, so I kept a copy of it called"
        f" {backup.name} in the same folder and started a fresh list."
    )


def _not_saved(error: OSError) -> dict:
    """The error a tool gives when the deadlines file cannot be written."""
    reason = error.strerror or type(error).__name__
    return {
        "status": "error",
        "message": f"I couldn't save your deadlines ({reason}), so nothing has changed. "
        "Please check the deadlines file and its folder are not read-only or open in another program, then try again.",
    }


def _title_key(title: str) -> str:
    """The form of a title used to compare titles, so titles that look the same match.

    NFKC turns look-alike characters into one standard form (a full-width A
    from an Asian keyboard becomes a plain A, and an accent typed as a separate
    mark joins its letter), casefold ignores upper and lower case, and
    split/join ignores extra spaces.
    """
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def _find(deadlines: list, title: str):
    """Return the saved deadline with this title, or None.

    Titles match when they look the same, so upper/lower case and extra spaces are ignored.
    """
    wanted = _title_key(title)
    for deadline in deadlines:
        if _title_key(deadline["title"]) == wanted:
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


# ---------- reminders ----------
#
# get_reminders (the tool) and Groot's instruction (in agent.py) both use
# _reminders below, so they always agree on what is overdue or due soon.


def _plural(count: int, word: str) -> str:
    """'1 day', '2 days'."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _time_phrase(due: datetime, now: datetime) -> str:
    """How long is left, or how late it is, in friendly words.

    On a different day we count whole calendar days ("tomorrow", "in 3 days",
    "2 days overdue"). On the same day we count hours, or minutes if it is
    under an hour. Part hours are dropped, so we never promise more time
    than there really is.
    """
    days = (due.date() - now.date()).days
    if days < 0:
        return f"{_plural(-days, 'day')} overdue"
    if days == 1:
        return "tomorrow"
    if days > 1:
        return f"in {_plural(days, 'day')}"

    # Same day, so count hours or minutes. They are counted in UTC, so the
    # count is still right on the nights the clocks change for daylight saving.
    minutes = int(abs((_utc(due) - _utc(now)).total_seconds()) // 60)
    if due < now:
        minutes = max(minutes, 1)  # a few seconds late still counts as late
    elif minutes == 0:
        return "right now"
    hours = minutes // 60
    amount = _plural(hours, "hour") if hours else _plural(minutes, "minute")
    return f"{amount} overdue" if due < now else f"in {amount}"


def _reminders(days_ahead: int) -> dict:
    """Unfinished deadlines that need attention, split into three groups.

    "overdue": the due time has already passed (most overdue first).
    "due_today": not passed yet and due some time today.
    "due_soon": due after today, at most days_ahead days from today.
    Each group is soonest first, so overdue starts with the most overdue.
    Each item has "title", "subject", "due_date" and "when" (a friendly
    phrase like "in 3 hours", "tomorrow" or "2 days overdue").
    """
    now = _now()
    last_day = now.date() + timedelta(days=days_ahead)
    groups = {"overdue": [], "due_today": [], "due_soon": []}

    with _file_lock:
        deadlines = _load_deadlines()
    for deadline in _soonest_first(deadlines):
        if deadline["done"]:
            continue
        due = _parse_due_date(deadline["due_date"])
        if due < now:
            group = "overdue"
        elif due.date() == now.date():
            group = "due_today"
        elif due.date() <= last_day:
            group = "due_soon"
        else:
            continue  # too far away to worry about yet
        groups[group].append({
            "title": deadline["title"],
            "subject": deadline["subject"],
            "due_date": deadline["due_date"],
            "when": _time_phrase(due, now),
        })
    return groups


# ---------- clash warnings ----------
#
# get_reminders, Groot's instruction (agent.py) and the home page all use
# _clashes below, so they always agree on which deadlines bunch up.


def _short_friendly(moment: datetime) -> str:
    """For example 'Sun 15 Nov, 8:59 PM'. Shorter than _friendly, for clash warnings."""
    weekday = WEEKDAY_NAMES[moment.weekday()][:3].title()
    month = MONTH_NAMES[moment.month - 1][:3].title()
    hour = moment.hour % 12 or 12
    am_pm = "AM" if moment.hour < 12 else "PM"
    return f"{weekday} {moment.day} {month}, {hour}:{moment.minute:02d} {am_pm}"


def _gap_phrase(minutes: int) -> str:
    """How far apart two deadlines are, for example 'only 27 hours apart'."""
    if minutes == 0:
        return "due at the same time"
    if minutes < 60:
        return "less than an hour apart"
    return f"only {_plural(minutes // 60, 'hour')} apart"  # part hours are dropped


def _clash_message(clash: dict, show=None) -> str:
    """One clash in friendly words, with a practical tip.

    show turns a title into the text to print. The tool shows titles as they
    are. agent.py passes its own function, so titles are made safe and put in
    quotes before they go into Groot's instruction.
    """
    show = show or (lambda title: title)
    items = clash["deadlines"]
    if clash["type"] == "close_together":
        first, second = items
        first_due = _short_friendly(_parse_due_date(first["due_date"]))
        second_due = _short_friendly(_parse_due_date(second["due_date"]))
        return (
            f"Your {show(first['title'])} ({first_due}) and {show(second['title'])} ({second_due}) are "
            f"{_gap_phrase(clash['minutes_apart'])}. Consider starting work on {show(first['title'])} a few days early."
        )
    names = [show(item["title"]) for item in items]
    listed = ", ".join(names[:-1]) + " and " + names[-1]
    monday = _short_friendly(datetime.fromisoformat(clash["week_start"])).split(",")[0]  # just 'Mon 16 Nov'
    return (
        f"You have {len(items)} deadlines in the week starting {monday}: {listed}. "
        "Try to finish one of them the week before."
    )


def _clashes(now: datetime | None = None, deadlines: list | None = None) -> list:
    """Unfinished, upcoming deadlines that bunch up, as a list of clashes.

    Two kinds of clash:
    "close_together": two deadlines next to each other in time that are due
        CLASH_HOURS (48) hours or less apart. Only neighbours are paired, so
        three deadlines in a row give two warnings, not three.
    "busy_week": BUSY_WEEK_COUNT (3) or more deadlines in the same Monday to
        Sunday week. Fixed weeks, like UTS teaching weeks, never overlap, so
        the same deadlines are not warned about twice.
    Finished deadlines and deadlines whose time has passed never count. A
    clash is only kept if its first deadline is due within CLASH_DAYS days,
    so the warnings stay about the next couple of weeks.
    Each clash has "type", "deadlines" (title, subject, due_date), "message",
    and "minutes_apart" or "week_start" ("YYYY-MM-DD", the Monday).
    """
    now = _now() if now is None else now
    if deadlines is None:
        with _file_lock:
            deadlines = _load_deadlines()
    last_day = now.date() + timedelta(days=CLASH_DAYS)

    # Upcoming, unfinished deadlines, soonest first. Ties are sorted by title so the order never changes.
    upcoming = [d for d in deadlines if not d["done"] and _parse_due_date(d["due_date"]) >= now]
    upcoming.sort(key=lambda d: (_parse_due_date(d["due_date"]), _title_key(d["title"])))
    short = [{"title": d["title"], "subject": d["subject"], "due_date": d["due_date"]} for d in upcoming]

    clashes = []
    for first, second in zip(short, short[1:]):
        # Counted in UTC, so the gap is right on the nights the clocks change
        gap = _utc(_parse_due_date(second["due_date"])) - _utc(_parse_due_date(first["due_date"]))
        if gap <= timedelta(hours=CLASH_HOURS):
            clashes.append({
                "type": "close_together",
                "deadlines": [first, second],
                "minutes_apart": int(gap.total_seconds() // 60),
            })

    weeks = {}  # the Monday of each week -> its deadlines
    for item in short:
        day = _parse_due_date(item["due_date"]).date()
        weeks.setdefault(day - timedelta(days=day.weekday()), []).append(item)
    for monday, items in weeks.items():
        if len(items) >= BUSY_WEEK_COUNT:
            clashes.append({"type": "busy_week", "deadlines": items, "week_start": monday.isoformat()})

    # Only the next couple of weeks, sorted by when each clash starts
    clashes = [c for c in clashes if _parse_due_date(c["deadlines"][0]["due_date"]).date() <= last_day]
    clashes.sort(key=lambda c: _parse_due_date(c["deadlines"][0]["due_date"]))
    for clash in clashes:
        clash["message"] = _clash_message(clash)
    return clashes


def _clash_sentence(count: int) -> str:
    """The short sentence get_reminders adds to its message when there are clashes."""
    if count == 0:
        return ""
    found = "1 clash" if count == 1 else f"{count} clashes"
    return f" I also spotted {found} where deadlines bunch up in the next {CLASH_DAYS} days."


# ---------- grades ----------
#
# grade_needed (the tool) and the home page's Grades section both use
# _grade_report below. Plain maths, no Gemini.


def _subject_parts(subject: str):
    """'41039 Programming Fundamentals' -> ('41039', 'Programming Fundamentals').

    A subject with no 5-digit UTS code in front gives (None, the whole subject).
    """
    match = re.fullmatch(r"([0-9]{5}) +(.+)", subject.strip())
    if match:
        return match[1], match[2]
    return None, subject.strip()


def _subject_matches(subject: str, wanted: str) -> bool:
    """True if wanted is the subject's code, its name or the whole subject (case is ignored)."""
    if not subject.strip():
        return False
    code, name = _subject_parts(subject)
    names = {_title_key(subject), _title_key(name)} | ({code} if code else set())
    return _title_key(wanted) in names


def _subjects(deadlines: list) -> list:
    """Every subject that has a deadline, in the order they first appear, ignoring repeats."""
    found = {}
    for deadline in deadlines:
        if deadline["subject"].strip():
            found.setdefault(_title_key(deadline["subject"]), deadline["subject"])
    return list(found.values())


def _number_text(value: float) -> str:
    """62.5 -> '62.5', 70.0 -> '70', 33.333 -> '33.3'."""
    return f"{round(value, 1):g}"


def _band_result(target: int, earned: float, still_to_come: float) -> dict:
    """What the student needs on the rest of a subject to reach one grade band.

    "result" is "secured" (already reached, even with 0 on everything left),
    "not_reachable" (more than 100% would be needed, or nothing is left) or
    "needed", with "needed_average" the average mark needed on the rest
    (rounded up to 1 decimal place).
    """
    if round(earned, 6) >= target:  # round first, so 64.9999999 from float maths still counts as 65
        return {"result": "secured", "needed_average": None}
    if still_to_come <= 0:
        return {"result": "not_reachable", "needed_average": None}
    needed = _round_up((target - earned) / still_to_come * 100)
    if needed > 100:
        return {"result": "not_reachable", "needed_average": needed}
    return {"result": "needed", "needed_average": needed}


def _round_up(value: float) -> float:
    """Round up to 1 decimal place, so 63.75 -> 63.8. It never says less is needed than really is.

    It rounds to 6 places first, so a tiny float error like 70.00000000001 stays 70.0.
    """
    return math.ceil(round(value * 10, 6)) / 10


def _grade_report(subject: str, items: list) -> dict:
    """The grade maths for one subject's deadlines. See grade_needed for what comes back.

    The final mark is out of 100. Each marked item with a weight adds
    weight x mark / 100 to the mark earned so far. Every bit of the 100 that
    is not marked yet is "still to come", including weight no deadline lists,
    because that part of the mark has not been earned yet either.
    """
    earned = 0.0
    marked_weight = 0.0
    listed_weight = 0.0
    no_weight = []
    for item in items:
        weight = item.get("weight_percent")
        if weight is None:
            no_weight.append(item["title"])
            continue
        listed_weight += weight
        if item.get("mark_percent") is not None:
            marked_weight += weight
            earned += weight * item["mark_percent"] / 100
    still_to_come = max(0.0, 100 - marked_weight)

    warnings = []
    if no_weight:
        warnings.append(
            f"{_plural(len(no_weight), 'item')} ({', '.join(no_weight)}) {'has' if len(no_weight) == 1 else 'have'}"
            " no weight, so they are left out of the maths. Add their weights from the subject outline."
        )
    if abs(listed_weight - 100) > 0.1:  # a little room, because thirds like 33.33 never add up exactly
        if listed_weight < 100:
            warnings.append(
                f"The weights add up to {_number_text(listed_weight)}%, not 100%, so the numbers below assume"
                " the missing part is still to come. Check the weights against the subject outline."
            )
        else:
            warnings.append(
                f"The weights add up to {_number_text(listed_weight)}%, which is more than 100%, so some are"
                " probably wrong and the numbers below are not reliable. Check the subject outline."
            )

    bands = {}
    for key, (band, target) in GRADE_BANDS.items():
        bands[key] = {"band": band, "target_percent": target, **_band_result(target, earned, still_to_come)}

    return {
        "subject": subject,
        "items": [
            {"title": item["title"], "weight_percent": item.get("weight_percent"),
             "mark_percent": item.get("mark_percent"), "done": item["done"]}
            for item in items
        ],
        "earned_percent": round(earned, 2),
        "marked_weight_percent": round(marked_weight, 2),
        "still_to_come_percent": round(still_to_come, 2),
        "listed_weight_percent": round(listed_weight, 2),
        "bands": bands,
        "warnings": warnings,
    }


def _band_sentence(band: dict) -> str:
    """For example 'To get a Credit (65), you need an average of 62.5% on what is left.'"""
    name = f"{band['band']} ({band['target_percent']})"
    if band["result"] == "secured":
        return f"You have already secured a {name}, even with 0 on everything left."
    if band["result"] == "not_reachable":
        if band["needed_average"] is None:
            return f"A {name} is no longer reachable, because nothing is left to mark."
        return (
            f"A {name} is no longer reachable, because you would need an average of "
            f"{_number_text(band['needed_average'])}% on what is left."
        )
    return f"To get a {name}, you need an average of {_number_text(band['needed_average'])}% on what is left."


def _all_grade_reports() -> list:
    """A grade report for every subject that has a deadline, for the home page."""
    with _file_lock:
        deadlines = _load_deadlines()
    return [
        _grade_report(subject, [d for d in deadlines if _title_key(d["subject"]) == _title_key(subject)])
        for subject in _subjects(deadlines)
    ]


def _days_ahead_error(days_ahead):
    """An error message if days_ahead is not a whole number from 1 to MAX_DAYS_AHEAD, otherwise None."""
    # Numbers from the model can arrive as 7.0 instead of 7, so whole floats are fine.
    # True and False count as numbers in Python, so they are refused on purpose.
    is_number = isinstance(days_ahead, (int, float)) and not isinstance(days_ahead, bool)
    if is_number and 1 <= days_ahead <= MAX_DAYS_AHEAD and float(days_ahead).is_integer():
        return None
    return f"days_ahead must be a whole number of days from 1 to {MAX_DAYS_AHEAD}, but I got {days_ahead!r}."


# ---------- calendar export ----------
#
# An iCalendar (.ics) file is the standard file that Google Calendar, Outlook
# and phone calendars can import. Its rules come from RFC 5545.

# Every line of an .ics file ends with a carriage return and a line feed.
CRLF = "\r\n"

# A line can be at most 75 bytes long (not counting CRLF). Longer lines are folded.
MAX_LINE_BYTES = 75


def _calendar_file() -> Path:
    """Where the calendar file is saved.

    Uses the DEADLINES_ICS_FILE environment variable if it is set. Otherwise it
    is deadlines.ics in the same folder as the deadlines file.
    """
    custom_path = os.environ.get("DEADLINES_ICS_FILE")
    if custom_path:
        return Path(custom_path)
    return _data_file().with_name("deadlines.ics")


def _ics_time(moment: datetime) -> str:
    """A UTC time written the iCalendar way, for example '20261120T125900Z' (Z means UTC)."""
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _ics_text(text: str) -> str:
    """Make text safe to put in an iCalendar file (RFC 5545 section 3.3.11).

    Backslashes, semicolons and commas have a special meaning in the file, so
    each one gets a backslash in front. A line break becomes the two
    characters \\n. Other control characters are not allowed, and a broken
    character (only possible in a hand-edited deadlines file) cannot be
    saved, so both become spaces.
    """
    text = text.replace("\\", "\\\\")  # first, so the backslashes added below are not doubled
    text = text.replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\r\n", "\n").replace("\n", "\\n")
    # Category "Cc" is control characters and "Cs" is half of a broken character
    return "".join(" " if unicodedata.category(char) in ("Cc", "Cs") else char for char in text)


def _fold(line: str) -> str:
    """Split a line longer than 75 bytes over several lines (RFC 5545 section 3.1).

    Each extra line starts with a space, which tells calendar apps to join it
    back on. Bytes are counted in UTF-8, and a character is never cut in
    half, so letters like é and emoji stay whole.
    """
    lines = []
    current, size = "", 0
    for char in line:
        char_size = len(char.encode("utf-8"))
        if size + char_size > MAX_LINE_BYTES:
            lines.append(current)
            current, size = " ", 1  # the space counts towards the next line's 75 bytes
        current += char
        size += char_size
    lines.append(current)
    return CRLF.join(lines)


def _uid(title: str) -> str:
    """A fixed ID for a deadline's calendar event, made from its title.

    The same title always gives the same ID, so importing the file again
    updates the event instead of adding a copy. It starts from the
    normalised title that Groot uses to match titles, so "Essay" and
    " essay " get the same ID. That is turned into a SHA-256 fingerprint,
    which is always 64 letters and digits, as the iCalendar rules for IDs allow.
    """
    # "replace" turns a broken character (only possible in a hand-edited file) into "?" instead of crashing
    return hashlib.sha256(_title_key(title).encode("utf-8", "replace")).hexdigest()


def _event_lines(deadline: dict, stamp: str) -> list:
    """The lines of one calendar event for a deadline, with a reminder 1 day before.

    stamp is when the file was made, in UTC.
    """
    start = _utc(_parse_due_date(deadline["due_date"]))
    end = start + timedelta(minutes=1)  # the end must come after the start, so each event lasts 1 minute
    title = _ics_text(deadline["title"])
    lines = [
        "BEGIN:VEVENT",
        "UID:" + _uid(deadline["title"]),
        "DTSTAMP:" + stamp,
        "DTSTART:" + _ics_time(start),
        "DTEND:" + _ics_time(end),
        "SUMMARY:" + title,
    ]
    if deadline["subject"]:
        lines.append("DESCRIPTION:" + _ics_text("Subject: " + deadline["subject"]))
    lines += [
        "BEGIN:VALARM",  # a pop-up reminder
        "ACTION:DISPLAY",
        "TRIGGER:-P1D",  # 1 day before the start
        f"DESCRIPTION:{title} is due tomorrow",
        "END:VALARM",
        "END:VEVENT",
    ]
    return lines


def _calendar_text(deadlines: list, stamp: str) -> str:
    """The whole .ics file for these deadlines, with long lines folded and CRLF line endings."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agent Groot//Deadline Export//EN",
        "CALSCALE:GREGORIAN",
        # PUBLISH means "a copy of some events". It also makes DTSTAMP mean "when this file was made".
        "METHOD:PUBLISH",
    ]
    for deadline in deadlines:
        lines += _event_lines(deadline, stamp)
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + CRLF for line in lines)


# ---------- the tools ----------


def add_deadline(title: str, due_date: str, subject: str = "", weight_percent: float | None = None) -> dict:
    """Saves a new deadline for the student.

    Args:
        title: Name of the task, for example "Assignment 1". Must be unique
            (upper/lower case and extra spaces are ignored).
        due_date: When it is due, in the student's own words exactly as they
            typed them. Do not convert it yourself, this tool works out the
            date using today's date in Sydney. Understood forms:
            "today", "tomorrow", "in 3 days", "in 2 weeks", "in 4 hours",
            "in 30 minutes", "friday" (the next Friday after today),
            "next friday" (the Friday of next week), "20 nov",
            "20 november 2026", "20/11", "20/11/2026" (day first),
            "end of the week", "end of next week", or "2026-11-20" and
            "2026-11-20 14:30". A day and month with no year means the next
            time that date comes round, so in November "20 jan" is next year.
            A time can be added to any of the date words, for example
            "next friday 5pm", "tomorrow 5:30pm" (or 5.30pm), "20 nov 17:00",
            "friday noon" or "friday midnight". With no time, it is due at
            the end of that day (11:59 PM).
        subject: Optional university subject, for example "Machine Learning".
        weight_percent: Optional share of the subject's final mark, from 0 to
            100, for example 30 for "worth 30%". Only give it if the student
            says it. It is used by grade_needed.

    Returns:
        A dict with "status" ("success" or "error") and a "message". On
        success it also has the saved "deadline", and the message shows the
        date in full (and points out a date in a later year) so the student
        can spot a mistake. If the date is unclear, does not exist or is in
        the past, the message explains why, so ask the student to check it.
        If the old deadlines file could not be read, the message names the
        backup copy that was kept, so tell the student about it.
    """
    now = _now()
    try:
        title = _text(title, "title")
        subject = _text(subject, "subject")
        weight = _percent(weight_percent, "weight_percent")
        if not title:
            raise ValueError("A deadline needs a title.")
        saved_date = _understand_due_date(_text(due_date, "due_date"), now)
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    new_deadline = {"title": title, "due_date": saved_date, "subject": subject, "done": False}
    if weight is not None:
        new_deadline["weight_percent"] = weight  # only added when known, so old-style deadlines stay the same
    with _file_lock:
        deadlines = _load_deadlines()
        existing = _find(deadlines, title)
        if existing is not None:
            return {
                "status": "error",
                "message": f"You already have a deadline called '{existing['title']}'. Pick a different title.",
            }
        deadlines.append(new_deadline)
        try:
            backup = _save_deadlines(deadlines)
        except OSError as error:
            return _not_saved(error)

    # Show the date in full so the student can spot a mistake, like the wrong year
    due = _parse_due_date(saved_date)
    message = f"Saved '{title}', due {_friendly(due)}."
    if due.year > now.year:
        message += f" That's in {due.year}, not this year."
    return {"status": "success", "message": message + _backup_note(backup), "deadline": new_deadline}


def list_deadlines() -> dict:
    """Lists every saved deadline, soonest first, including finished ones.

    If the student only wants what is overdue or due soon, use get_reminders instead.

    Returns:
        A dict with "status", a "message" and "deadlines", a list where each
        item has "title", "due_date", "subject" and "done" (True if finished).
        A due_date is Sydney time, either "YYYY-MM-DD HH:MM" or just
        "YYYY-MM-DD", which means due by 11:59 PM that day.
    """
    with _file_lock:
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
    with no time is still upcoming until the end of that day. To see
    everything overdue or due soon, use get_reminders instead.

    Returns:
        A dict with "status", a "message" and "deadline" (the next one, or
        None if nothing is coming up).
    """
    now = _now()
    with _file_lock:
        deadlines = _load_deadlines()
    upcoming = [
        d for d in deadlines
        if not d["done"] and _parse_due_date(d["due_date"]) >= now
    ]
    if not upcoming:
        return {"status": "success", "message": "You have no upcoming deadlines.", "deadline": None}

    soonest = _soonest_first(upcoming)[0]
    # Spell out the weekday and the time (like 11:59 PM), so the model does not have to work them out
    due = _friendly(_parse_due_date(soonest["due_date"]))
    return {
        "status": "success",
        "message": f"Your next deadline is '{soonest['title']}', due {due}.",
        "deadline": soonest,
    }


def delete_deadline(title: str) -> dict:
    """Permanently deletes a saved deadline.

    Args:
        title: The title of the deadline to delete (upper/lower case and extra spaces are ignored).

    Returns:
        A dict with "status" ("success" or "error") and a "message".
    """
    try:
        title = _text(title, "title")
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    with _file_lock:
        deadlines = _load_deadlines()
        found = _find(deadlines, title)
        if found is None:
            return _not_found(title)
        deadlines.remove(found)
        try:
            backup = _save_deadlines(deadlines)
        except OSError as error:
            return _not_saved(error)
    return {"status": "success", "message": f"Deleted '{found['title']}'." + _backup_note(backup)}


def mark_done(title: str) -> dict:
    """Marks a saved deadline as finished.

    Args:
        title: The title of the deadline that is done (upper/lower case and extra spaces are ignored).

    Returns:
        A dict with "status" ("success" or "error") and a "message".
    """
    try:
        title = _text(title, "title")
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    with _file_lock:
        deadlines = _load_deadlines()
        found = _find(deadlines, title)
        if found is None:
            return _not_found(title)
        found["done"] = True
        try:
            backup = _save_deadlines(deadlines)
        except OSError as error:
            return _not_saved(error)
    return {"status": "success", "message": f"Marked '{found['title']}' as done." + _backup_note(backup)}


def edit_deadline(
    title: str,
    new_title: str = "",
    new_due_date: str = "",
    new_subject: str = "",
    remove_subject: bool = False,
) -> dict:
    """Changes a saved deadline's title, due date or subject, without deleting it.

    Call this when the student wants to rename a deadline, move it to another
    date or change its subject, like "move Quiz 2 to next monday 5pm" or
    "rename Essay to Final Essay". Only give the things that change, and
    leave the rest out. Its weight, its mark and whether it is done stay as
    they are (use set_mark or mark_done for those).

    Args:
        title: The current title of the deadline (upper/lower case and extra spaces are ignored).
        new_title: The new title. Leave it out to keep the title. It must not
            be the title of another deadline.
        new_due_date: The new due date in the student's own words exactly as
            they typed them, the same forms as add_deadline, for example
            "next monday 5pm". Do not convert it yourself. Leave it out to
            keep the date.
        new_subject: The new subject. Leave it out to keep the subject.
        remove_subject: True only if the student asks to remove the subject.

    Returns:
        A dict with "status" ("success" or "error"), a "message" and, on
        success, the updated "deadline". A new date is shown in full so the
        student can spot a mistake. If the new date is unclear, does not
        exist or is in the past, nothing is changed and the message says why.
    """
    now = _now()
    try:
        title = _text(title, "title")
        new_title = _text(new_title, "new_title")
        new_subject = _text(new_subject, "new_subject")
        date_words = _text(new_due_date, "new_due_date")
        if not isinstance(remove_subject, bool):
            raise ValueError(f"remove_subject must be true or false, but I got {remove_subject!r}.")
        new_date = _understand_due_date(date_words, now) if date_words else None
    except ValueError as error:
        return {"status": "error", "message": str(error)}
    if new_subject and remove_subject:
        return {"status": "error", "message": "Give a new subject or ask to remove it, not both."}
    if not (new_title or new_date or new_subject or remove_subject):
        return {"status": "error", "message": "Tell me what to change: the title, the due date or the subject."}

    with _file_lock:
        deadlines = _load_deadlines()
        found = _find(deadlines, title)
        if found is None:
            return _not_found(title)
        old_title = found["title"]
        changes = []
        if new_title and new_title != found["title"]:
            other = _find(deadlines, new_title)
            if other is not None and other is not found:  # only a change of upper/lower case finds itself
                return {
                    "status": "error",
                    "message": f"You already have a deadline called '{other['title']}'. Pick a different title.",
                }
            found["title"] = new_title
            changes.append(f"renamed it to '{new_title}'")
        if new_date and new_date != found["due_date"]:
            found["due_date"] = new_date
            due = _parse_due_date(new_date)
            change = f"moved it to {_friendly(due)}"
            if due.year > now.year:
                change += f" (that's in {due.year}, not this year)"
            changes.append(change)
        if remove_subject and found["subject"]:
            found["subject"] = ""
            changes.append("removed its subject")
        elif new_subject and new_subject != found["subject"]:
            found["subject"] = new_subject
            changes.append(f"set its subject to '{new_subject}'")
        if not changes:
            return {"status": "success", "message": f"'{old_title}' already looks like that, so nothing changed.", "deadline": found}
        try:
            backup = _save_deadlines(deadlines)
        except OSError as error:
            return _not_saved(error)

    listed = changes[0] if len(changes) == 1 else ", ".join(changes[:-1]) + " and " + changes[-1]
    return {"status": "success", "message": f"Updated '{old_title}': {listed}." + _backup_note(backup), "deadline": found}


def get_reminders(days_ahead: int = REMINDER_DAYS) -> dict:
    """Finds unfinished deadlines that are overdue, due today or due soon.

    Call this when the student asks things like "what's due soon?",
    "anything overdue?", "what do I need to do this week?" or "remind me
    what's coming up". Finished deadlines are never included. Tell the
    student about them briefly and kindly, using the "when" phrases.

    Args:
        days_ahead: How many days ahead counts as "due soon", from 1 to 60.
            Use 7 unless the student asks about a different period, for
            example 14 for "the next two weeks" or 1 for "by tomorrow".

    Returns:
        A dict with "status" ("success" or "error") and a friendly "message".
        On success it also has three lists:
        "overdue" (the due time has passed, most overdue first),
        "due_today" (still to come today) and
        "due_soon" (after today, within days_ahead days, soonest first).
        Each item has "title", "subject", "due_date" and "when", a phrase
        like "in 3 hours", "tomorrow", "in 4 days" or "2 days overdue".
        It also has "clashes": unfinished deadlines in the next 7 days that
        are due within 48 hours of each other, or 3 or more in one Monday to
        Sunday week. Each clash has a ready "message" with a tip. Mention
        them kindly and briefly, never as something scary.
    """
    error = _days_ahead_error(days_ahead)
    if error:
        return {"status": "error", "message": error}
    days_ahead = int(days_ahead)

    groups = _reminders(days_ahead)
    period = f"the next {_plural(days_ahead, 'day')}"
    parts = []
    if groups["overdue"]:
        parts.append(f"{len(groups['overdue'])} overdue")
    if groups["due_today"]:
        parts.append(f"{len(groups['due_today'])} due today")
    if groups["due_soon"]:
        parts.append(f"{len(groups['due_soon'])} due in {period}")

    if not parts:
        message = f"Good news, nothing is overdue and nothing is due in {period}. You're all caught up!"
    elif len(parts) == 1:
        message = f"Heads up, you have {parts[0]}."
    else:
        message = f"Heads up, you have {', '.join(parts[:-1])} and {parts[-1]}."
    clashes = _clashes()  # always the next CLASH_DAYS days, so the chat and the home page agree
    return {"status": "success", "message": message + _clash_sentence(len(clashes)), **groups, "clashes": clashes}


def set_mark(title: str, mark_percent: float | None = None, weight_percent: float | None = None) -> dict:
    """Saves the student's mark for a deadline, its weight, or both.

    Call this when the student tells you a result, like "I got 78 on Quiz 1"
    or "my essay got 16 out of 20" (work out the percentage, here 80), or
    tells you how much a task is worth, like "Quiz 1 is worth 10%". A mark
    means the task is finished, so the deadline is also marked as done.

    Args:
        title: The title of the deadline (upper/lower case and extra spaces are ignored).
        mark_percent: The student's result as a percentage from 0 to 100.
            Leave it out to change only the weight.
        weight_percent: The task's share of the subject's final mark, from 0
            to 100. Leave it out to keep the weight it already has.

    Returns:
        A dict with "status" ("success" or "error"), a "message" and, on
        success, the updated "deadline".
    """
    try:
        title = _text(title, "title")
        mark = _percent(mark_percent, "mark_percent")
        weight = _percent(weight_percent, "weight_percent")
    except ValueError as error:
        return {"status": "error", "message": str(error)}
    if mark is None and weight is None:
        return {"status": "error", "message": "Tell me the mark (0 to 100), the weight (0 to 100) or both."}

    with _file_lock:
        deadlines = _load_deadlines()
        found = _find(deadlines, title)
        if found is None:
            return _not_found(title)
        changes = []
        if weight is not None:
            found["weight_percent"] = weight
            changes.append(f"its weight to {_number_text(weight)}%")
        if mark is not None:
            found["mark_percent"] = mark
            found["done"] = True  # a task with a mark is finished
            changes.insert(0, f"your mark to {_number_text(mark)}%")
        try:
            backup = _save_deadlines(deadlines)
        except OSError as error:
            return _not_saved(error)

    message = f"Set {' and '.join(changes)} for '{found['title']}'."
    if mark is not None:
        message += " It is marked as done too."
    return {"status": "success", "message": message + _backup_note(backup), "deadline": found}


def grade_needed(subject: str, target: str = "credit") -> dict:
    """Works out what average mark the student needs on the rest of a subject.

    Call this when the student asks things like "what do I need on the exam
    to pass?", "can I still get a distinction in 41039?" or "how am I going
    in Programming Fundamentals?". It uses the weights and marks saved with
    each deadline (see set_mark). The UTS grade bands are Pass 50, Credit 65,
    Distinction 75 and High Distinction 85. Many subjects also have minimum
    rules (for example at least 40% on the exam) that this cannot check, so
    remind the student to read their subject outline.

    Args:
        subject: The subject's code or name, for example "41039" or
            "Programming Fundamentals" (upper/lower case is ignored).
        target: The band the student cares about: "pass", "credit",
            "distinction" or "high distinction" (or "hd"). Use "credit" if
            they do not say.

    Returns:
        A dict with "status" ("success" or "error") and a "message" that
        answers for the target band. On success it also has:
        "earned_percent" (marks earned towards the final mark so far),
        "still_to_come_percent" (the part of the final mark not marked yet),
        "bands" (for every band: "result" is "secured", "needed" or
        "not_reachable", and "needed_average" is the average needed on the
        rest), "items" (each deadline's weight and mark) and "warnings"
        (for example weights that are missing or do not add up to 100).
        Always pass the warnings on.
    """
    try:
        subject = _text(subject, "subject")
        target_text = _text(target, "target").lower() or "credit"
    except ValueError as error:
        return {"status": "error", "message": str(error)}
    target_key = BAND_NICKNAMES.get(target_text, target_text)
    if target_key not in GRADE_BANDS:
        return {
            "status": "error",
            "message": f"I don't know the grade '{target_text}'. Use pass, credit, distinction or high distinction.",
        }
    if not subject:
        return {"status": "error", "message": "Tell me which subject, by its code (like 41039) or its name."}

    with _file_lock:
        deadlines = _load_deadlines()
    found = [d for d in deadlines if _subject_matches(d["subject"], subject)]
    if not found:
        known = _subjects(deadlines)
        listed = f" Your subjects are: {', '.join(known)}." if known else " No deadline has a subject yet."
        return {"status": "error", "message": f"I couldn't find a subject called '{subject}'.{listed}"}
    names = _subjects(found)
    if len(names) > 1:
        return {
            "status": "error",
            "message": f"'{subject}' matches more than one subject: {', '.join(names)}. Which one do you mean?",
        }

    report = _grade_report(names[0], found)
    message = (
        f"{names[0]}: you have earned {_number_text(report['earned_percent'])}% of the final mark so far, and "
        f"{_number_text(report['still_to_come_percent'])}% is still to come. "
        + _band_sentence(report["bands"][target_key])
    )
    for warning in report["warnings"]:
        message += " Warning: " + warning
    message += " Some subjects also have minimum rules, like a minimum exam mark, so check the subject outline."
    return {"status": "success", "message": message, "target": target_key, **report}


def export_calendar() -> dict:
    """Saves every unfinished deadline to a calendar file (deadlines.ics) the student can import.

    Call this when the student asks things like "add these to my calendar",
    "export my deadlines" or "put my deadlines in Google Calendar, Outlook or
    my phone". Finished deadlines are left out. Each deadline becomes an
    event at its due time, with a reminder 1 day before.

    After it works, tell the student where the file is and, in one or two
    short sentences, how to import it: in Google Calendar on a computer, open
    Settings, then Import & export, and choose the file, and it then shows up
    on any iPhone or Android phone signed in to the same Google account. On
    an iPhone they can also email the file to themselves, tap it in the Mail
    app and tap Add All.

    Returns:
        A dict with "status" ("success" or "error") and a "message". On
        success the message gives the file's location and how many deadlines
        it holds, and "exported" is that number. When there is nothing
        unfinished, "exported" is 0 and no file is written.
    """
    stamp = _ics_time(_utc(_now()))
    path = _calendar_file()
    with _file_lock:
        unfinished = [d for d in _soonest_first(_load_deadlines()) if not d["done"]]
        if not unfinished:
            # A calendar file must hold at least one event, so there is no file to make
            return {
                "status": "success",
                "message": "You have no unfinished deadlines, so there is nothing to put in a calendar yet.",
                "exported": 0,
            }
        try:
            _replace_file(path, _calendar_text(unfinished, stamp))
        except OSError as error:
            reason = error.strerror or type(error).__name__
            return {
                "status": "error",
                "message": f"I couldn't save your calendar file ({reason}). Please check its folder is not "
                "read-only and the file is not open in another program, then try again.",
            }
    count = len(unfinished)
    return {
        "status": "success",
        "message": f"I saved {_plural(count, 'unfinished deadline')} to this calendar file: {path}",
        "exported": count,
    }
