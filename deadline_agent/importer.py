"""Turn the outline items, timetable and Canvas feed into rows the student checks.

Plain code, no AI. build_preview follows the "How dates are decided" rules
in docs/superpowers/specs/2026-11-04-outline-dropbox-design.md:

1. Each outline item becomes one row (or one row per week for a weekly item),
   with a date from the UTS calendar and a status saying how sure it is.
2. A Canvas event that clearly matches a row gives that row its exact date.
   Canvas events that match nothing become extra rows.
3. Rows on a NSW public holiday are flagged, and rows already past start unticked.

Nothing is saved until save_rows is called with the rows the student confirmed.
"""

import re
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher

from . import tools, uts_calendar
from .import_types import CanvasEvent, ExtractedItem, PreviewRow, TimetableClass

# Used when the outline names no day or no time
DEFAULT_WEEKDAY = "friday"
DEFAULT_TIME = "23:59"

# Matching Canvas events to outline items by name
MIN_SIMILARITY = 0.6  # difflib ratio a name needs to be a possible match
NUMBER_BONUS = 0.3  # added when both names have the same numbers, like "Assignment 2"
CLEAR_MARGIN = 0.1  # how far the best match must be ahead of the next best to be merged

NO_DATE_NOTE = "The outline gives no usable date for this, so check Canvas or your subject's announcements."
ALL_DAY_NOTE = " Canvas has it as an all-day event, so 11:59 PM was used."


def build_preview(
    extracted_items: list[ExtractedItem],
    session: str,
    timetable: dict[str, list[TimetableClass]] | None = None,
    canvas_events: list[CanvasEvent] | None = None,
    chosen_subjects: list[str] | None = None,
    now: datetime | None = None,
) -> list[PreviewRow]:
    """The rows of the review table, outline rows first, then Canvas-only rows.

    Args:
        extracted_items: What the outline reader found, from every outline.
        session: "AUT2026" or "SPR2026". Any other session raises ValueError.
        timetable: From timetable.read_timetable, used for tutorial days.
        canvas_events: From canvas.parse_feed.
        chosen_subjects: Subject codes to include. Items, classes and Canvas
            events for any other subject (like 48023 when the student has no
            outline for it) are ignored. Defaults to the subjects in extracted_items.
        now: The time to compare dates with. Defaults to tools._now().
    """
    uts_calendar.session_info(session)  # raises ValueError for an unknown session
    now = tools._now() if now is None else now
    if chosen_subjects is None:
        chosen = {item["subject_code"] for item in extracted_items}
    else:
        chosen = set(chosen_subjects)
    timetable = timetable or {}

    # Keep each row next to its item, so Canvas matching can use the item's name
    outline = []
    for item in extracted_items:
        if item["subject_code"] in chosen:
            classes = timetable.get(item["subject_code"], [])
            outline += [(item, row) for row in _outline_rows(item, session, classes)]

    events = [event for event in canvas_events or [] if event["subject_code"] in chosen]
    subject_names = {item["subject_code"]: item["subject_name"] for item in extracted_items}
    canvas_rows = _apply_canvas(outline, events, subject_names)

    rows = [row for _, row in outline] + canvas_rows
    for row in rows:
        _check_date(row, now)
        row["include"] = row["status"] in ("exact", "assumed")
    return rows


def save_rows(rows: list[PreviewRow]) -> list[dict]:
    """Save the rows the student confirmed, each through tools.add_deadline.

    A row's due_date may be a date the student typed in, which add_deadline
    checks as usual. Returns add_deadline's result for each row, in the same
    order. A row that cannot be saved (no date, a date in the past, a title
    already used) gets an error result, and the other rows are still saved.
    """
    return [tools.add_deadline(row["title"], row["due_date"], row["subject"]) for row in rows]


# ---------- one outline item becomes one or more rows ----------


def _row(item: ExtractedItem, status: str, due: datetime | None, note: str) -> PreviewRow:
    """A row for an outline item. due is None when the date is not known."""
    return {
        "title": f"{item['subject_code']} {item['name']}",
        "subject": f"{item['subject_code']} {item['subject_name']}",
        "weight_percent": item["weight_percent"],
        "due_date": None if due is None else due.strftime("%Y-%m-%d %H:%M"),
        "status": status,
        "source": "outline",
        "note": note,
        "include": False,  # set at the end of build_preview
    }


def _outline_rows(item: ExtractedItem, session: str, classes: list[TimetableClass]) -> list[PreviewRow]:
    """The rows for one outline item, following the rules table in the spec."""
    when = item["when"]
    if when == "date":
        return [_date_row(item)]
    if when == "week":
        return [_week_row(item, session)]
    if when == "tutorial":
        return [_tutorial_row(item, session, classes)]
    if when == "recurring":
        return _recurring_rows(item, session)
    if when == "exam_period":
        first, last = uts_calendar.session_info(session)["exams"]
        note = (
            f"The outline says this is in the exam period ({tools._friendly_day(first)} to "
            f"{tools._friendly_day(last)}), so check the UTS exam timetable for the date."
        )
        return [_row(item, "unknown", None, note)]
    if when == "unknown":
        return [_row(item, "unknown", None, NO_DATE_NOTE)]
    raise ValueError(f"Unknown 'when' value {when!r} for '{item['name']}'.")


def _is_teaching_week(week) -> bool:
    return week is not None and 1 <= week <= uts_calendar.LAST_WEEK


def _not_a_week_note(week, session: str) -> str:
    """The note for a row whose week is missing or is not a teaching week."""
    if week is None:
        return "The outline does not say which week, so the date is unknown."
    name = uts_calendar.session_info(session)["name"]
    return f"The outline says week {week}, but {name} only has teaching weeks 1 to 12, so the date is unknown."


def _date_row(item: ExtractedItem) -> PreviewRow:
    """The outline gives a calendar date, with or without a time."""
    if item["date"] is None:
        return _row(item, "unknown", None, NO_DATE_NOTE)
    if item["time"]:
        due = tools._parse_due_date(f"{item['date']} {item['time']}")
        return _row(item, "exact", due, "The outline gives the date and time.")
    due = tools._parse_due_date(item["date"])  # a date alone means 23:59
    return _row(item, "exact", due, "The outline gives the date but no time, so 11:59 PM was used.")


def _week_row(item: ExtractedItem, session: str) -> PreviewRow:
    """The outline gives a teaching week, maybe with a day or a time."""
    week, weekday, time = item["week"], item["weekday"], item["time"]
    if not _is_teaching_week(week):
        return _row(item, "unknown", None, _not_a_week_note(week, session))

    if weekday:
        due = uts_calendar.week_date(session, week, weekday, time or DEFAULT_TIME)
        note = f"The outline says {weekday.title()} of week {week}"
        note += "." if time else " with no time, so 11:59 PM was used."
        return _row(item, "exact", due, note)

    # No day, so Friday is assumed. A time alone does not say which day.
    due = uts_calendar.week_date(session, week, DEFAULT_WEEKDAY, time or DEFAULT_TIME)
    if time:
        note = f"The outline says week {week} at {time} with no day, so Friday of week {week} was assumed."
    else:
        note = f"The outline says week {week} with no day, so Friday of week {week} at 11:59 PM was assumed."
    return _row(item, "assumed", due, note)


def _tutorials(classes: list[TimetableClass]) -> list[TimetableClass]:
    """A subject's tutorial classes: its Tut activities, or its Wrk ones if it has no Tut."""
    for kind in ("Tut", "Wrk"):
        found = [one for one in classes if one["activity"].startswith(kind)]
        if found:
            return found
    return []


def _tutorial_row(item: ExtractedItem, session: str, classes: list[TimetableClass]) -> PreviewRow:
    """The outline says it happens in the tutorial, maybe in a given week."""
    week = item["week"]
    if week is None:
        note = "The outline says this happens in your tutorial but gives no week, so please type the date."
        return _row(item, "needs_input", None, note)
    if not _is_teaching_week(week):
        return _row(item, "unknown", None, _not_a_week_note(week, session))

    tutorials = _tutorials(classes)
    times = {(one["weekday"], one["start"]) for one in tutorials}
    if len(times) != 1:
        found = "no tutorial time" if not times else "more than one tutorial time"
        monday = tools._friendly_day(uts_calendar.week_start(session, week))
        note = (
            f"The outline says your tutorial in week {week}, but {found} for this subject was found in your "
            f"timetable, so please type the date. Week {week} starts on {monday}."
        )
        return _row(item, "needs_input", None, note)

    weekday, start = times.pop()
    due = uts_calendar.week_date(session, week, weekday, start)
    note = (
        f"The outline says your tutorial in week {week}, and your timetable has your "
        f"{tutorials[0]['activity']} class on {weekday.title()} at {start}."
    )
    return _row(item, "exact", due, note)


def _recurring_rows(item: ExtractedItem, session: str) -> list[PreviewRow]:
    """The outline says it happens every week, so make one row per teaching week."""
    first, last, weekday, time = item["first_week"], item["last_week"], item["weekday"], item["time"]
    if first is None:
        note = "The outline says this happens every week but not from which week, so the date is unknown."
        return [_row(item, "unknown", None, note)]
    end_note = ""
    if last is None:
        # "Each week from week 4" means until the end of teaching
        last = uts_calendar.LAST_WEEK
        end_note = f" The outline gives no last week, so week {last} was used."
    if not (_is_teaching_week(first) and _is_teaching_week(last) and first <= last):
        note = f"The outline says weeks {first} to {last}, but teaching weeks run from 1 to 12, so the date is unknown."
        return [_row(item, "unknown", None, note)]

    if weekday:
        note = f"The outline says every {weekday.title()} from week {first} to week {last}"
        note += "." if time else " with no time, so 11:59 PM was used."
    else:
        note = f"The outline says every week from week {first} to week {last} with no day, so Friday was assumed."
    # A row is only exact when the outline names the day and the last week
    status = "exact" if weekday and not end_note else "assumed"

    rows = []
    for week, _monday in uts_calendar.teaching_weeks(session, first, last):  # StuVac is skipped
        due = uts_calendar.week_date(session, week, weekday or DEFAULT_WEEKDAY, time or DEFAULT_TIME)
        row = _row(item, status, due, note + end_note)
        row["title"] += f" (week {week})"  # every saved title must be different
        rows.append(row)
    return rows


# ---------- matching Canvas events to outline rows ----------


def _normalise(name: str) -> str:
    """'Assignment 2: Report!' -> 'assignment 2 report', so case and punctuation do not matter."""
    text = unicodedata.normalize("NFKC", name).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def _numbers(name: str) -> set[int]:
    """The small numbers in a normalised name, like {2} in 'assignment 2'."""
    return {int(number) for number in re.findall(r"\b[0-9]{1,3}\b", name)}


def _similarity(canvas_title: str, item: ExtractedItem) -> float | None:
    """How alike a Canvas title and an outline item's name are.

    Returns None if they cannot be the same thing: the difflib ratio is below
    0.6, or both have numbers and the numbers differ ("Skills Test 1" is
    never "Skills Test 2"). The same numbers on both sides are a strong hint,
    so they add NUMBER_BONUS. An item with no number in its name uses its
    assessment task number instead.
    """
    canvas_name, item_name = _normalise(canvas_title), _normalise(item["name"])
    ratio = SequenceMatcher(None, canvas_name, item_name).ratio()
    if ratio < MIN_SIMILARITY:
        return None
    canvas_numbers, item_numbers = _numbers(canvas_name), _numbers(item_name)
    if not item_numbers and item["task_number"] is not None:
        item_numbers = {item["task_number"]}
    if canvas_numbers and item_numbers:
        if canvas_numbers != item_numbers:
            return None
        return ratio + NUMBER_BONUS
    return ratio


def _apply_canvas(outline: list, events: list[CanvasEvent], subject_names: dict[str, str]) -> list[PreviewRow]:
    """Merge each Canvas event into the outline row it clearly matches.

    outline is a list of (item, row) pairs. A match must be in the same
    subject and clearly better (by CLEAR_MARGIN) than the next best row. If
    it is not clear, or two events pick the same row, nothing is merged:
    the event gets its own row and both sides are flagged in their notes.
    Returns the rows for the events that were not merged.
    """
    picks = {}  # event position -> position of the outline row it clearly matches
    close = {}  # event position -> positions of every outline row it might match
    for event_at, event in enumerate(events):
        scored = []
        for row_at, (item, _) in enumerate(outline):
            if item["subject_code"] == event["subject_code"]:
                score = _similarity(event["title"], item)
                if score is not None:
                    scored.append((score, row_at))
        scored.sort(reverse=True)  # best first
        if scored:
            close[event_at] = [row_at for _, row_at in scored]
        if len(scored) == 1 or (len(scored) > 1 and scored[0][0] - scored[1][0] >= CLEAR_MARGIN):
            picks[event_at] = scored[0][1]

    times_picked = Counter(picks.values())
    flagged_rows = set()
    extra_rows = []
    for event_at, event in enumerate(events):
        pick = picks.get(event_at)
        if pick is not None and times_picked[pick] == 1:
            _merge(outline[pick][1], event)
            continue
        if event_at in close:
            note = "Canvas lists this, and it might be an outline row too, so it was not merged. Check for a duplicate."
            flagged_rows.update(close[event_at])
        else:
            note = "Only Canvas lists this."
        extra_rows.append(_canvas_row(event, subject_names, note))

    for row_at in flagged_rows:
        outline[row_at][1]["note"] += " A Canvas event might be this one too, so check for a duplicate."
    return extra_rows


def _merge(row: PreviewRow, event: CanvasEvent) -> None:
    """Give an outline row the date of the Canvas event that matches it."""
    outline_date = row["due_date"]
    if outline_date is None:
        note = "The date comes from Canvas, because the outline did not give one."
    elif outline_date == event["due"]:
        note = "The date comes from Canvas and matches the outline."
    else:
        outline_due = tools._friendly(tools._parse_due_date(outline_date))
        note = f"The date comes from Canvas. The outline suggested {outline_due}."
    row["due_date"] = event["due"]
    row["status"] = "exact"
    row["source"] = "both"
    row["note"] = note + (ALL_DAY_NOTE if event["all_day"] else "")


def _canvas_row(event: CanvasEvent, subject_names: dict[str, str], note: str) -> PreviewRow:
    """A row for a Canvas event that was not merged into an outline row."""
    code = event["subject_code"]
    name = subject_names.get(code)
    return {
        "title": f"{code} {event['title']}",
        "subject": f"{code} {name}" if name else code,
        "weight_percent": None,
        "due_date": event["due"],
        "status": "exact",
        "source": "canvas",
        "note": note + (ALL_DAY_NOTE if event["all_day"] else ""),
        "include": False,  # set at the end of build_preview
    }


# ---------- checks for every row with a date ----------


def _check_date(row: PreviewRow, now: datetime) -> None:
    """Flag a date on a public holiday, and mark a date that has passed as past."""
    if row["due_date"] is None:
        return
    due = tools._parse_due_date(row["due_date"])
    if uts_calendar.is_public_holiday(due.date()):
        holiday = uts_calendar.PUBLIC_HOLIDAYS[due.date()]
        row["note"] += f" {tools._friendly_day(due)} is a NSW public holiday ({holiday}), so check this date."
        if row["status"] == "exact":
            row["status"] = "assumed"  # a date on a holiday is at best assumed
    if due < now:
        row["status"] = "past"
        row["note"] += " This date has already passed."
