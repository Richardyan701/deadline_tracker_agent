"""Tests for the UTS 2026 calendar.

The Monday of every teaching week is written out by hand below from the
official UTS 2026 Assessment Planner (Main calendar), so a mistake in the
code's week counting cannot hide behind the same mistake in the test.
"""

from datetime import date, datetime, timedelta

import pytest

from deadline_agent import uts_calendar

# The Monday each teaching week starts, copied from the planner
AUTUMN_WEEKS = {
    1: date(2026, 2, 16), 2: date(2026, 2, 23), 3: date(2026, 3, 2), 4: date(2026, 3, 9),
    5: date(2026, 3, 16), 6: date(2026, 3, 23), 7: date(2026, 3, 30),
    # StuVac 6 to 12 Apr
    8: date(2026, 4, 13), 9: date(2026, 4, 20), 10: date(2026, 4, 27), 11: date(2026, 5, 4), 12: date(2026, 5, 11),
}
SPRING_WEEKS = {
    1: date(2026, 7, 27), 2: date(2026, 8, 3), 3: date(2026, 8, 10), 4: date(2026, 8, 17),
    5: date(2026, 8, 24), 6: date(2026, 8, 31), 7: date(2026, 9, 7), 8: date(2026, 9, 14),
    # StuVac 21 to 27 Sep
    9: date(2026, 9, 28), 10: date(2026, 10, 5), 11: date(2026, 10, 12), 12: date(2026, 10, 19),
}
PLANNER = [("AUT2026", week, monday) for week, monday in AUTUMN_WEEKS.items()]
PLANNER += [("SPR2026", week, monday) for week, monday in SPRING_WEEKS.items()]


# ---------- teaching weeks ----------


@pytest.mark.parametrize("session, week, monday", PLANNER)
def test_every_week_starts_on_the_planner_date(session, week, monday):
    assert uts_calendar.week_start(session, week) == monday


@pytest.mark.parametrize("session, week, monday", PLANNER)
def test_every_week_starts_on_a_monday(session, week, monday):
    assert uts_calendar.week_start(session, week).weekday() == 0


def test_sessions_have_twelve_teaching_weeks():
    assert len(uts_calendar.session_info("AUT2026")["weeks"]) == 12
    assert len(uts_calendar.session_info("SPR2026")["weeks"]) == 12


def test_session_names():
    assert uts_calendar.session_info("AUT2026")["name"] == "Autumn 2026"
    assert uts_calendar.session_info("SPR2026")["name"] == "Spring 2026"


# ---------- StuVac and exams ----------


def test_both_stuvac_weeks_match_the_planner():
    assert uts_calendar.session_info("AUT2026")["stuvac"] == [date(2026, 4, 6), date(2026, 5, 18)]
    assert uts_calendar.session_info("SPR2026")["stuvac"] == [date(2026, 9, 21), date(2026, 10, 26)]


def test_mid_session_stuvac_sits_between_the_weeks_around_it():
    # Autumn: week 7 is followed by StuVac, then week 8 a week later
    assert uts_calendar.week_start("AUT2026", 7) + timedelta(weeks=1) == date(2026, 4, 6)
    assert uts_calendar.week_start("AUT2026", 8) == date(2026, 4, 6) + timedelta(weeks=1)
    # Spring: week 8 is followed by StuVac, then week 9 a week later
    assert uts_calendar.week_start("SPR2026", 8) + timedelta(weeks=1) == date(2026, 9, 21)
    assert uts_calendar.week_start("SPR2026", 9) == date(2026, 9, 21) + timedelta(weeks=1)


def test_final_stuvac_comes_straight_after_week_12():
    assert uts_calendar.week_start("AUT2026", 12) + timedelta(weeks=1) == date(2026, 5, 18)
    assert uts_calendar.week_start("SPR2026", 12) + timedelta(weeks=1) == date(2026, 10, 26)


def test_exam_periods_match_the_planner():
    assert uts_calendar.session_info("AUT2026")["exams"] == (date(2026, 5, 25), date(2026, 6, 12))
    assert uts_calendar.session_info("SPR2026")["exams"] == (date(2026, 11, 2), date(2026, 11, 20))


@pytest.mark.parametrize("session", ["AUT2026", "SPR2026"])
def test_no_teaching_day_falls_in_stuvac_or_the_exams(session):
    info = uts_calendar.session_info(session)
    stuvac_days = {monday + timedelta(days=i) for monday in info["stuvac"] for i in range(7)}
    first_exam, last_exam = info["exams"]
    for week in range(1, 13):
        for weekday in uts_calendar.WEEKDAY_NAMES:
            day = uts_calendar.week_date(session, week, weekday, "12:00").date()
            assert day not in stuvac_days
            assert not first_exam <= day <= last_exam


def test_exams_start_the_monday_after_the_final_stuvac():
    for session in ["AUT2026", "SPR2026"]:
        info = uts_calendar.session_info(session)
        assert info["exams"][0] == info["stuvac"][1] + timedelta(weeks=1)


# ---------- week_date ----------


@pytest.mark.parametrize(
    "session, week, weekday, time, expected",
    [
        ("SPR2026", 7, "friday", "23:59", datetime(2026, 9, 11, 23, 59)),
        ("SPR2026", 8, "sunday", "17:30", datetime(2026, 9, 20, 17, 30)),  # the last day before StuVac
        ("SPR2026", 9, "monday", "09:00", datetime(2026, 9, 28, 9, 0)),  # the first day after StuVac
        ("SPR2026", 12, "friday", "23:59", datetime(2026, 10, 23, 23, 59)),
        ("AUT2026", 1, "monday", "00:00", datetime(2026, 2, 16, 0, 0)),
        ("AUT2026", 7, "friday", "23:59", datetime(2026, 4, 3, 23, 59)),
        ("AUT2026", 8, "wednesday", "14:00", datetime(2026, 4, 15, 14, 0)),
    ],
)
def test_week_date(session, week, weekday, time, expected):
    assert uts_calendar.week_date(session, week, weekday, time) == expected


# ---------- teaching_weeks ----------


def test_teaching_weeks_skip_spring_stuvac():
    assert uts_calendar.teaching_weeks("SPR2026", 7, 10) == [
        (7, date(2026, 9, 7)),
        (8, date(2026, 9, 14)),
        # 21 Sep is StuVac, so it is not here
        (9, date(2026, 9, 28)),
        (10, date(2026, 10, 5)),
    ]


def test_teaching_weeks_skip_autumn_stuvac():
    assert uts_calendar.teaching_weeks("AUT2026", 6, 9) == [
        (6, date(2026, 3, 23)),
        (7, date(2026, 3, 30)),
        # 6 Apr is StuVac, so it is not here
        (8, date(2026, 4, 13)),
        (9, date(2026, 4, 20)),
    ]


def test_teaching_weeks_one_week_and_all_weeks():
    assert uts_calendar.teaching_weeks("SPR2026", 4, 4) == [(4, date(2026, 8, 17))]
    assert uts_calendar.teaching_weeks("SPR2026", 1, 12) == list(SPRING_WEEKS.items())


@pytest.mark.parametrize("first, last", [(5, 4), (0, 3), (10, 13), (12, 1)])
def test_teaching_weeks_refuses_bad_ranges(first, last):
    with pytest.raises(ValueError):
        uts_calendar.teaching_weeks("SPR2026", first, last)


# ---------- bad input ----------


@pytest.mark.parametrize("session", ["SUM2026", "spr2026", "AUT2025", "", "Spring 2026"])
def test_unknown_session_is_a_clear_error(session):
    with pytest.raises(ValueError, match="Unknown session"):
        uts_calendar.session_info(session)
    with pytest.raises(ValueError, match="Unknown session"):
        uts_calendar.week_start(session, 1)
    with pytest.raises(ValueError, match="Unknown session"):
        uts_calendar.week_date(session, 1, "friday", "23:59")
    with pytest.raises(ValueError, match="Unknown session"):
        uts_calendar.teaching_weeks(session, 1, 2)


@pytest.mark.parametrize("week", [0, 13, -1, 100, 5.0, True, None, "5"])
def test_week_outside_1_to_12_is_a_clear_error(week):
    with pytest.raises(ValueError, match="not a teaching week"):
        uts_calendar.week_start("SPR2026", week)
    with pytest.raises(ValueError, match="not a teaching week"):
        uts_calendar.week_date("SPR2026", week, "friday", "23:59")


@pytest.mark.parametrize("weekday", ["Friday", "fri", "", "funday", None])
def test_bad_weekday_is_a_clear_error(weekday):
    with pytest.raises(ValueError, match="weekday"):
        uts_calendar.week_date("SPR2026", 3, weekday, "23:59")


@pytest.mark.parametrize("time", ["24:00", "9:00", "12:60", "noon", "", "5pm", "23:59:00"])
def test_bad_time_is_a_clear_error(time):
    with pytest.raises(ValueError, match="HH:MM"):
        uts_calendar.week_date("SPR2026", 3, "friday", time)


# ---------- public holidays ----------


@pytest.mark.parametrize(
    "day, name",
    [
        (date(2026, 4, 3), "Good Friday"),
        (date(2026, 4, 4), "Easter Saturday"),
        (date(2026, 4, 5), "Easter Sunday"),
        (date(2026, 4, 25), "Anzac Day"),
        (date(2026, 4, 27), "the extra Anzac Day holiday"),
        (date(2026, 10, 5), "Labour Day"),
    ],
)
def test_public_holidays_in_teaching_weeks(day, name):
    assert uts_calendar.is_public_holiday(day)
    assert uts_calendar.PUBLIC_HOLIDAYS[day] == name


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 8, 3),  # the Bank Holiday is only for banks
        date(2026, 10, 6),
        date(2026, 4, 2),
        date(2026, 4, 26),
        date(2026, 9, 11),
    ],
)
def test_ordinary_days_are_not_public_holidays(day):
    assert not uts_calendar.is_public_holiday(day)


def test_every_listed_holiday_is_in_a_teaching_week():
    for day in uts_calendar.PUBLIC_HOLIDAYS:
        mondays = AUTUMN_WEEKS.values() if day.month < 7 else SPRING_WEEKS.values()
        assert any(monday <= day <= monday + timedelta(days=6) for monday in mondays), day
