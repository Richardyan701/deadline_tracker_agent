"""The official UTS 2026 calendar, used to turn "week 7" into a real date.

Outlines give due dates as teaching weeks, like "due in week 7". Teaching
weeks are not evenly spaced, because each session has a study week (StuVac)
in the middle that has no week number. So the dates come from the official
calendar below, never from counting weeks.

Weeks start on Monday. Dates are plain Sydney dates and times with no
timezone attached, the same as the saved due dates in tools.py.

UTS dates come from the UTS "2026 Assessment Planners" (Main calendar) and the
UTS 2026 academic year dates page:
https://drupal.uts.edu.au/sites/default/files/article/downloads/2026AssessmentPlanners_CalendarMain.pdf
https://www.uts.edu.au/for-students/current-students/managing-your-course/important-dates/academic-year-dates/2026-academic-year-dates
"""

import re
from datetime import date, datetime, timedelta

from .tools import WEEKDAY_NAMES

# Every session has teaching weeks 1 to 12.
LAST_WEEK = 12


def _mondays(first: date, count: int) -> list[date]:
    """count Mondays in a row, one week apart, starting at first."""
    return [first + timedelta(weeks=i) for i in range(count)]


SESSIONS = {
    "AUT2026": {
        "name": "Autumn 2026",
        # Weeks 1 to 7 start on 16 Feb. After StuVac, weeks 8 to 12 start on 13 Apr.
        "weeks": _mondays(date(2026, 2, 16), 7) + _mondays(date(2026, 4, 13), 5),
        # The Mondays of the two StuVac weeks: 6 to 12 Apr and 18 to 24 May
        "stuvac": [date(2026, 4, 6), date(2026, 5, 18)],
        "exams": (date(2026, 5, 25), date(2026, 6, 12)),
    },
    "SPR2026": {
        "name": "Spring 2026",
        # Weeks 1 to 8 start on 27 Jul. After StuVac, weeks 9 to 12 start on 28 Sep.
        "weeks": _mondays(date(2026, 7, 27), 8) + _mondays(date(2026, 9, 28), 4),
        # The Mondays of the two StuVac weeks: 21 to 27 Sep and 26 Oct to 1 Nov
        "stuvac": [date(2026, 9, 21), date(2026, 10, 26)],
        "exams": (date(2026, 11, 2), date(2026, 11, 20)),
    },
}

# NSW public holidays that fall in the 2026 teaching weeks above.
# Source: the NSW Government list at https://www.nsw.gov.au/about-nsw/public-holidays
# The extra Monday after Anzac Day was announced on 15 Feb 2026:
# https://www.nsw.gov.au/ministerial-releases/minns-labor-government-announces-extra-public-holiday-year
# Left out on purpose: Easter Monday 6 Apr (in Autumn StuVac), King's Birthday
# 8 Jun (in the Autumn exams) and the Bank Holiday 3 Aug (only for banks, so
# not a public holiday for everyone).
PUBLIC_HOLIDAYS = {
    date(2026, 4, 3): "Good Friday",  # Autumn week 7
    date(2026, 4, 4): "Easter Saturday",  # Autumn week 7
    date(2026, 4, 5): "Easter Sunday",  # Autumn week 7
    date(2026, 4, 25): "Anzac Day",  # Autumn week 9
    date(2026, 4, 27): "the extra Anzac Day holiday",  # Autumn week 10
    date(2026, 10, 5): "Labour Day",  # Spring week 10
}


def session_info(session: str) -> dict:
    """The calendar for a session code, "AUT2026" or "SPR2026".

    Returns a dict with "name" (like "Spring 2026"), "weeks" (the Monday of
    each teaching week, week 1 first), "stuvac" (the Monday of each StuVac
    week) and "exams" (the first and last day of the exam period).
    Raises ValueError for any other session code.
    """
    if session not in SESSIONS:
        raise ValueError(f"Unknown session {session!r}. Use one of: {', '.join(SESSIONS)}.")
    return SESSIONS[session]


def week_start(session: str, week: int) -> date:
    """The Monday that a teaching week starts on.

    Raises ValueError for an unknown session or a week outside 1 to 12.
    """
    weeks = session_info(session)["weeks"]
    # True and False count as numbers in Python, so they are refused on purpose
    if not isinstance(week, int) or isinstance(week, bool) or not 1 <= week <= LAST_WEEK:
        raise ValueError(f"Week {week!r} is not a teaching week. Teaching weeks run from 1 to {LAST_WEEK}.")
    return weeks[week - 1]


def _clock(time: str) -> tuple[int, int]:
    """'17:30' -> (17, 30). Raises ValueError unless it is a real 24 hour 'HH:MM' time."""
    match = re.fullmatch(r"([01][0-9]|2[0-3]):([0-5][0-9])", time)
    if not match:
        raise ValueError(f"The time must be 24 hour 'HH:MM', like '17:30', but I got {time!r}.")
    return int(match[1]), int(match[2])


def week_date(session: str, week: int, weekday: str, time: str) -> datetime:
    """The date and time for a weekday in a teaching week.

    For example ("SPR2026", 7, "friday", "23:59") is Friday 11 Sep 2026 at 23:59.
    weekday is "monday" to "sunday" and time is 24 hour "HH:MM".
    Raises ValueError if any of them is not valid.
    """
    if weekday not in WEEKDAY_NAMES:
        raise ValueError(f"The weekday must be one of {', '.join(WEEKDAY_NAMES)}, but I got {weekday!r}.")
    hour, minute = _clock(time)
    day = week_start(session, week) + timedelta(days=WEEKDAY_NAMES.index(weekday))
    return datetime(day.year, day.month, day.day, hour, minute)


def teaching_weeks(session: str, first: int, last: int) -> list[tuple[int, date]]:
    """Every teaching week from first to last, as (week number, Monday) pairs.

    StuVac has no week number, so it is never in the list. For example in
    Spring 2026, weeks 8 to 9 are (8, 14 Sep) and (9, 28 Sep), and the StuVac
    week of 21 Sep is skipped.
    Raises ValueError for an unknown session, a week outside 1 to 12, or a
    first week that comes after the last week.
    """
    if first > last:
        raise ValueError(f"The first week ({first}) comes after the last week ({last}).")
    return [(week, week_start(session, week)) for week in range(first, last + 1)]


def is_public_holiday(day: date) -> bool:
    """True if the day is one of the NSW public holidays in PUBLIC_HOLIDAYS."""
    return day in PUBLIC_HOLIDAYS
