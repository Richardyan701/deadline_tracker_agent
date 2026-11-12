"""The shapes of the data passed between the parts of the outline drop box.

A TypedDict is a normal dict. The class below it only tells the reader (and
tools like type checkers) which keys the dict has and what type each one is.
The fields follow the "Data formats" section of
docs/superpowers/specs/2026-11-04-outline-dropbox-design.md.
"""

from typing import Literal, TypedDict


class ExtractedItem(TypedDict):
    """One dated item that the outline reader found in a subject outline."""

    subject_code: str  # five digits, for example "33130"
    subject_name: str  # for example "Mathematics 1"
    name: str  # for example "Skills Test 1", at most 120 characters
    task_number: int | None  # the outline's assessment task number, if any
    weight_percent: float | None  # this item's share of the final mark
    when: Literal["date", "week", "tutorial", "recurring", "exam_period", "unknown"]
    date: str | None  # "YYYY-MM-DD" when `when` is "date"
    week: int | None  # teaching week when `when` is "week" or "tutorial"
    first_week: int | None  # for "recurring", for example 4 ...
    last_week: int | None  # ... and 12 for "each week from week 4"
    weekday: str | None  # "monday" to "sunday", only if the outline names a day
    time: str | None  # "HH:MM" 24-hour, only if the outline names a time
    quote: str  # the outline's own words for the timing, at most 200 characters


class TimetableClass(TypedDict):
    """One class from the student's UTS timetable, for example a tutorial."""

    activity: str  # for example "Tut1", "Wrk1" or "Cmp1"
    weekday: str  # "monday" to "sunday", from the first date the class runs
    start: str  # "HH:MM" 24-hour, for example "09:00"
    end: str  # "HH:MM" 24-hour, for example "11:00"


class CanvasEvent(TypedDict):
    """One event from the student's Canvas calendar feed."""

    subject_code: str  # the first five-digit number in the title, or "" if there is none
    title: str  # the event's title, without the course tag in square brackets
    due: str  # Sydney time, "YYYY-MM-DD HH:MM"
    all_day: bool  # True if Canvas has a date but no time
    uid: str  # Canvas's own id for the event


class PreviewRow(TypedDict):
    """One row of the review table the student checks before saving."""

    title: str  # subject code plus item name, for example "33130 Skills Test 1"
    subject: str  # for example "33130 Mathematics 1"
    weight_percent: float | None  # as extracted, or None
    due_date: str | None  # "YYYY-MM-DD HH:MM", or None when the date is not known
    status: Literal["exact", "assumed", "needs_input", "unknown", "past"]
    source: Literal["outline", "canvas", "both"]
    note: str  # plain sentences explaining where the date came from
    include: bool  # whether the Save checkbox starts ticked
