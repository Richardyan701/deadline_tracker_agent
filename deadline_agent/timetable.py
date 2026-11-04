"""Read the class times from a UTS timetable export PDF. Plain code, no AI.

The PDF is a week grid. When pypdf reads its text, the grid's columns are
lost and each class comes out as a block of lines like this:

    9:00 - 11:00            the time range
    33130_SPR_U_1_S         the subject code, then the session
    Mathematics 1           the subject name, sometimes wrapped over two lines
    Tut1                    the activity, for example Tut1, Wrk1 or Cmp1
    03                      the class number
    AB01.02.300             the room
    4/8-15/9, 29/9-20/10    the dates it runs, as day/month

The blocks come one after another, after a Mon to Fri header and the hour
labels, and the text ends with "All Weeks". Because the columns are lost,
the weekday comes from the first date the class runs (4/8 is a Tuesday).
"""

import io
import re
from datetime import date

import pypdf

from . import uts_calendar
from .import_types import TimetableClass
from .tools import WEEKDAY_NAMES

# The patterns are used with .match, which only looks at the start of a line.
# A "$" at the end means the whole line must match.
TIME_RANGE = re.compile(r"([01]?[0-9]|2[0-3]):([0-5][0-9]) *[-–] *([01]?[0-9]|2[0-3]):([0-5][0-9])$")
CLASS_CODE = re.compile(r"([0-9]{5})_[A-Z0-9_]+$")  # "33130_SPR_U_1_S"
ACTIVITY = re.compile(r"[A-Z][a-z]{2}[0-9]+$")  # "Tut1", three letters and a number
FIRST_DATE = re.compile(r"([0-9]{1,2})/([0-9]{1,2})(?= *[-,]|$)")  # "4/8" in "4/8-15/9, 29/9-20/10"

# The line at the end of the class list
END_MARK = "All Weeks"


def read_timetable(pdf: bytes, session: str) -> dict[str, list[TimetableClass]]:
    """The classes in a UTS timetable export PDF, grouped by subject code.

    For example {"33130": [{"activity": "Tut1", "weekday": "tuesday",
    "start": "09:00", "end": "11:00"}]}. session ("AUT2026" or "SPR2026")
    gives the year of the dates. Raises ValueError if the file is not a PDF
    or does not look like a UTS timetable.
    """
    try:
        pages = pypdf.PdfReader(io.BytesIO(pdf)).pages
        text = "\n".join(page.extract_text() for page in pages)
    except pypdf.errors.PyPdfError as error:
        raise ValueError("The timetable could not be read as a PDF.") from error
    return parse_timetable(text, session)


def parse_timetable(text: str, session: str) -> dict[str, list[TimetableClass]]:
    """The classes in the text of a UTS timetable export, grouped by subject code.

    This is the part of read_timetable that does not need a PDF, so the
    tests can give it text directly. Raises ValueError if no class is found
    or a class block is missing its subject code, activity or dates.
    """
    year = uts_calendar.week_start(session, 1).year  # also checks the session
    timetable = {}
    for block in _blocks(text):
        code, found = _read_block(block, year)
        timetable.setdefault(code, []).append(found)
    if not timetable:
        raise ValueError("No classes were found. Is this the PDF export of your UTS timetable?")
    return timetable


def _blocks(text: str) -> list[list[str]]:
    """Split the text into one list of lines per class.

    A class starts at a time range line and runs until the next one, or
    until "All Weeks". Lines before the first class (the weekday header and
    hour labels) and empty lines are skipped.
    """
    blocks = []
    inside_a_class = False
    for line in text.splitlines():
        line = line.strip()
        if TIME_RANGE.match(line):
            blocks.append([line])
            inside_a_class = True
        elif line == END_MARK:
            inside_a_class = False
        elif line and inside_a_class:
            blocks[-1].append(line)
    return blocks


def _find_line(block: list[str], start: int, pattern: re.Pattern, what: str) -> int:
    """The position of the first line in the block, from start on, that matches pattern.

    Raises ValueError naming what was missing if no line matches.
    """
    for position in range(start, len(block)):
        if pattern.match(block[position]):
            return position
    raise ValueError(
        f"I couldn't find {what} for the class at {block[0]} in the timetable. "
        "Is this the PDF export of your UTS timetable?"
    )


def _read_block(block: list[str], year: int) -> tuple[str, TimetableClass]:
    """Read one class block. Returns its subject code and the class.

    The fields are found by their pattern rather than by counting lines, so
    a subject name or a list of dates wrapped over extra lines still works.
    """
    start_hour, start_minute, end_hour, end_minute = TIME_RANGE.match(block[0]).groups()
    code_at = _find_line(block, 1, CLASS_CODE, "the subject code")
    # The subject name comes between the code and the activity, so skip at least one line
    activity_at = _find_line(block, code_at + 2, ACTIVITY, "the activity (like Tut1)")
    dates_at = _find_line(block, activity_at + 1, FIRST_DATE, "the dates")

    day, month = FIRST_DATE.match(block[dates_at]).groups()
    try:
        first_day = date(year, int(month), int(day))
    except ValueError:
        raise ValueError(f"The class at {block[0]} starts on {day}/{month}, which is not a real date.") from None

    found: TimetableClass = {
        "activity": block[activity_at],
        "weekday": WEEKDAY_NAMES[first_day.weekday()],
        "start": f"{int(start_hour):02d}:{start_minute}",
        "end": f"{int(end_hour):02d}:{end_minute}",
    }
    return CLASS_CODE.match(block[code_at])[1], found
