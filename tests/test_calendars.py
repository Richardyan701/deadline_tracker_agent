"""Tests for the university calendars (UTS, UNSW, USyd and Macquarie).

The Monday of every teaching week is written out by hand below from each
university's official calendar, so a mistake in the code's week counting
cannot hide behind the same mistake in the test. The sources are listed at
the top of deadline_agent/calendars.py.
"""

from datetime import date, datetime, timedelta

import pytest

from deadline_agent import calendars


def d(day: int, month: int, year: int = 2027) -> date:
    """A short way to write a date the way the official calendars do: day, then month."""
    return date(year, month, day)


# The Monday each teaching week starts, week 1 first. A comment marks each break with no week number.
WEEKS = {
    # UTS 2026, copied from the 2026 Assessment Planner
    "AUT2026": [
        d(16, 2, 2026), d(23, 2, 2026), d(2, 3, 2026), d(9, 3, 2026), d(16, 3, 2026), d(23, 3, 2026), d(30, 3, 2026),
        # StuVac 6 to 12 Apr
        d(13, 4, 2026), d(20, 4, 2026), d(27, 4, 2026), d(4, 5, 2026), d(11, 5, 2026),
    ],
    "SPR2026": [
        d(27, 7, 2026), d(3, 8, 2026), d(10, 8, 2026), d(17, 8, 2026),
        d(24, 8, 2026), d(31, 8, 2026), d(7, 9, 2026), d(14, 9, 2026),
        # StuVac 21 to 27 Sep
        d(28, 9, 2026), d(5, 10, 2026), d(12, 10, 2026), d(19, 10, 2026),
    ],
    # UTS 2027: session starts Mon 15 Feb, mid-session StuVac 12 to 16 Apr, formal classes end Fri 14 May
    "AUT2027": [
        d(15, 2), d(22, 2), d(1, 3), d(8, 3), d(15, 3), d(22, 3), d(29, 3), d(5, 4),
        # StuVac 12 to 16 Apr
        d(19, 4), d(26, 4), d(3, 5), d(10, 5),
    ],
    # Session starts Mon 26 Jul, mid-session StuVac 20 to 24 Sep, formal classes end Fri 22 Oct
    "SPR2027": [
        d(26, 7), d(2, 8), d(9, 8), d(16, 8), d(23, 8), d(30, 8), d(6, 9), d(13, 9),
        # StuVac 20 to 24 Sep
        d(27, 9), d(4, 10), d(11, 10), d(18, 10),
    ],
    # UNSW 2027: ten weeks in a row, week 6 is flexibility week
    "UNSW_T1_2027": [d(15, 2), d(22, 2), d(1, 3), d(8, 3), d(15, 3), d(22, 3), d(29, 3), d(5, 4), d(12, 4), d(19, 4)],
    "UNSW_T2_2027": [d(31, 5), d(7, 6), d(14, 6), d(21, 6), d(28, 6), d(5, 7), d(12, 7), d(19, 7), d(26, 7), d(2, 8)],
    "UNSW_T3_2027": [
        d(13, 9), d(20, 9), d(27, 9), d(4, 10), d(11, 10), d(18, 10), d(25, 10), d(1, 11), d(8, 11), d(15, 11),
    ],
    # USyd 2027: teaching weeks 22 Feb to 30 May, mid-semester break 29 Mar to 4 Apr
    "USYD_S1_2027": [
        d(22, 2), d(1, 3), d(8, 3), d(15, 3), d(22, 3),
        # mid-semester break 29 Mar to 4 Apr
        d(5, 4), d(12, 4), d(19, 4), d(26, 4), d(3, 5), d(10, 5), d(17, 5), d(24, 5),
    ],
    # Teaching weeks 2 Aug to 7 Nov, mid-semester break 27 Sep to 4 Oct (Mon 4 Oct is Labour Day)
    "USYD_S2_2027": [
        d(2, 8), d(9, 8), d(16, 8), d(23, 8), d(30, 8), d(6, 9), d(13, 9), d(20, 9),
        # mid-semester break from 27 Sep
        d(4, 10), d(11, 10), d(18, 10), d(25, 10), d(1, 11),
    ],
    # Macquarie 2027: classes 22 Feb to 6 Jun, recess 12 to 25 Apr
    "MQ_S1_2027": [
        d(22, 2), d(1, 3), d(8, 3), d(15, 3), d(22, 3), d(29, 3), d(5, 4),
        # recess 12 to 25 Apr
        d(26, 4), d(3, 5), d(10, 5), d(17, 5), d(24, 5), d(31, 5),
    ],
    # Classes 26 Jul to 7 Nov, recess 20 Sep to 4 Oct (Mon 4 Oct is Labour Day)
    "MQ_S2_2027": [
        d(26, 7), d(2, 8), d(9, 8), d(16, 8), d(23, 8), d(30, 8), d(6, 9), d(13, 9),
        # recess from 20 Sep
        d(4, 10), d(11, 10), d(18, 10), d(25, 10), d(1, 11),
    ],
}
EVERY_WEEK = [(session, number, monday) for session, mondays in WEEKS.items() for number, monday in enumerate(mondays, 1)]

# The last day of teaching each official calendar gives: a Friday at UTS and UNSW, a Sunday at USyd and Macquarie
LAST_TEACHING_DAY = {
    "AUT2026": d(15, 5, 2026), "SPR2026": d(23, 10, 2026),
    "AUT2027": d(14, 5), "SPR2027": d(22, 10),
    "UNSW_T1_2027": d(23, 4), "UNSW_T2_2027": d(6, 8), "UNSW_T3_2027": d(19, 11),
    "USYD_S1_2027": d(30, 5), "USYD_S2_2027": d(7, 11),
    "MQ_S1_2027": d(6, 6), "MQ_S2_2027": d(7, 11),
}  # fmt: skip

# The first and last day of each exam period
EXAMS = {
    "AUT2026": (d(25, 5, 2026), d(12, 6, 2026)), "SPR2026": (d(2, 11, 2026), d(20, 11, 2026)),
    "AUT2027": (d(24, 5), d(11, 6)), "SPR2027": (d(1, 11), d(19, 11)),
    "UNSW_T1_2027": (d(30, 4), d(13, 5)), "UNSW_T2_2027": (d(13, 8), d(26, 8)), "UNSW_T3_2027": (d(26, 11), d(9, 12)),
    "USYD_S1_2027": (d(7, 6), d(19, 6)), "USYD_S2_2027": (d(15, 11), d(27, 11)),
    "MQ_S1_2027": (d(7, 6), d(25, 6)), "MQ_S2_2027": (d(8, 11), d(26, 11)),
}  # fmt: skip


# ---------- every session is covered ----------


def test_the_tests_cover_every_session_in_the_calendar():
    assert set(WEEKS) == set(calendars.SESSIONS)
    assert set(LAST_TEACHING_DAY) == set(calendars.SESSIONS)
    assert set(EXAMS) == set(calendars.SESSIONS)


def test_every_session_belongs_to_a_known_university():
    for info in calendars.SESSIONS.values():
        assert info["university"] in calendars.UNIVERSITIES


def test_every_university_has_a_2027_session():
    for key in calendars.UNIVERSITIES:
        assert any(info["university"] == key and "2027" in info["name"] for info in calendars.SESSIONS.values()), key


# ---------- teaching weeks ----------


@pytest.mark.parametrize("session, week, monday", EVERY_WEEK)
def test_every_week_starts_on_the_official_date(session, week, monday):
    assert calendars.week_start(session, week) == monday


@pytest.mark.parametrize("session, week, monday", EVERY_WEEK)
def test_every_week_starts_on_a_monday(session, week, monday):
    assert calendars.week_start(session, week).weekday() == 0


@pytest.mark.parametrize(
    "session, weeks",
    [
        ("AUT2026", 12), ("SPR2026", 12), ("AUT2027", 12), ("SPR2027", 12),
        ("UNSW_T1_2027", 10), ("UNSW_T2_2027", 10), ("UNSW_T3_2027", 10),
        ("USYD_S1_2027", 13), ("USYD_S2_2027", 13),
        ("MQ_S1_2027", 13), ("MQ_S2_2027", 13),
    ],
)  # fmt: skip
def test_each_university_has_its_own_number_of_teaching_weeks(session, weeks):
    assert len(calendars.session_info(session)["weeks"]) == weeks
    assert calendars.last_week(session) == weeks


@pytest.mark.parametrize("session, last_day", LAST_TEACHING_DAY.items())
def test_teaching_ends_on_the_official_day(session, last_day):
    last_monday = calendars.week_start(session, calendars.last_week(session))
    # The official day is the Friday or the Sunday of the last teaching week
    assert last_day in (last_monday + timedelta(days=4), last_monday + timedelta(days=6))


def test_session_names():
    names = {code: info["name"] for code, info in calendars.SESSIONS.items()}
    assert names == {
        "AUT2026": "Autumn 2026", "SPR2026": "Spring 2026", "AUT2027": "Autumn 2027", "SPR2027": "Spring 2027",
        "UNSW_T1_2027": "Term 1 2027", "UNSW_T2_2027": "Term 2 2027", "UNSW_T3_2027": "Term 3 2027",
        "USYD_S1_2027": "Semester 1 2027", "USYD_S2_2027": "Semester 2 2027",
        "MQ_S1_2027": "Session 1 2027", "MQ_S2_2027": "Session 2 2027",
    }  # fmt: skip


@pytest.mark.parametrize(
    "session, name",
    [("SPR2027", "UTS"), ("UNSW_T2_2027", "UNSW"), ("USYD_S1_2027", "USyd"), ("MQ_S2_2027", "Macquarie")],
)
def test_university_name(session, name):
    assert calendars.university_name(session) == name


# ---------- breaks and exams ----------


@pytest.mark.parametrize(
    "session, breaks",
    [
        ("AUT2026", [d(6, 4, 2026), d(18, 5, 2026)]),  # mid-session StuVac, final StuVac
        ("SPR2026", [d(21, 9, 2026), d(26, 10, 2026)]),
        ("AUT2027", [d(12, 4), d(17, 5)]),
        ("SPR2027", [d(20, 9), d(25, 10)]),
        ("UNSW_T1_2027", [d(26, 4)]),  # only the study period, because flexibility week is week 6
        ("UNSW_T2_2027", [d(9, 8)]),
        ("UNSW_T3_2027", [d(22, 11)]),
        ("USYD_S1_2027", [d(29, 3), d(31, 5)]),  # mid-semester break, STUVAC
        ("USYD_S2_2027", [d(27, 9), d(8, 11)]),
        ("MQ_S1_2027", [d(12, 4), d(19, 4)]),  # the two recess weeks
        ("MQ_S2_2027", [d(20, 9), d(27, 9)]),
    ],
)
def test_breaks_match_the_official_calendars(session, breaks):
    assert calendars.session_info(session)["breaks"] == breaks


def test_uts_mid_session_stuvac_sits_between_the_weeks_around_it():
    # Autumn 2026: week 7 is followed by StuVac, then week 8 a week later
    assert calendars.week_start("AUT2026", 7) + timedelta(weeks=1) == date(2026, 4, 6)
    assert calendars.week_start("AUT2026", 8) == date(2026, 4, 6) + timedelta(weeks=1)
    # Spring 2026: week 8 is followed by StuVac, then week 9 a week later
    assert calendars.week_start("SPR2026", 8) + timedelta(weeks=1) == date(2026, 9, 21)
    assert calendars.week_start("SPR2026", 9) == date(2026, 9, 21) + timedelta(weeks=1)
    # Both 2027 sessions: week 8, StuVac, week 9
    assert calendars.week_start("AUT2027", 9) - calendars.week_start("AUT2027", 8) == timedelta(weeks=2)
    assert calendars.week_start("SPR2027", 9) - calendars.week_start("SPR2027", 8) == timedelta(weeks=2)


def test_usyd_break_is_one_week_and_macquarie_recess_is_two():
    assert calendars.week_start("USYD_S1_2027", 6) - calendars.week_start("USYD_S1_2027", 5) == timedelta(weeks=2)
    assert calendars.week_start("USYD_S2_2027", 9) - calendars.week_start("USYD_S2_2027", 8) == timedelta(weeks=2)
    assert calendars.week_start("MQ_S1_2027", 8) - calendars.week_start("MQ_S1_2027", 7) == timedelta(weeks=3)
    assert calendars.week_start("MQ_S2_2027", 9) - calendars.week_start("MQ_S2_2027", 8) == timedelta(weeks=3)


@pytest.mark.parametrize("session", ["UNSW_T1_2027", "UNSW_T2_2027", "UNSW_T3_2027"])
def test_unsw_weeks_are_all_in_a_row(session):
    weeks = calendars.session_info(session)["weeks"]
    assert all(later - earlier == timedelta(weeks=1) for earlier, later in zip(weeks, weeks[1:]))


@pytest.mark.parametrize(
    "session, monday, sunday",
    [
        ("UNSW_T1_2027", d(22, 3), d(28, 3)),  # "Flexibility week T1 | 22 March - 28 March"
        ("UNSW_T2_2027", d(5, 7), d(11, 7)),  # "Flexibility week T2 | 5 July - 11 July"
        ("UNSW_T3_2027", d(18, 10), d(24, 10)),  # "Flexibility week T3 | 18 Oct - 24 Oct"
    ],
)
def test_unsw_week_6_is_flexibility_week(session, monday, sunday):
    assert calendars.quiet_week(session, 6) == "flexibility week"
    assert calendars.week_start(session, 6) == monday
    assert calendars.week_start(session, 6) + timedelta(days=6) == sunday
    assert [week for week in range(1, 11) if calendars.quiet_week(session, week)] == [6]


@pytest.mark.parametrize("session", ["AUT2026", "SPR2027", "USYD_S1_2027", "MQ_S2_2027"])
def test_other_universities_have_no_quiet_week(session):
    assert all(calendars.quiet_week(session, week) is None for week in range(1, 14))


@pytest.mark.parametrize("session, exams", EXAMS.items())
def test_exam_periods_match_the_official_calendars(session, exams):
    assert calendars.session_info(session)["exams"] == exams


@pytest.mark.parametrize("session", list(calendars.SESSIONS))
def test_no_teaching_day_falls_in_a_break_or_the_exams(session):
    info = calendars.session_info(session)
    break_days = {monday + timedelta(days=i) for monday in info["breaks"] for i in range(7)}
    first_exam, last_exam = info["exams"]
    for week in range(1, calendars.last_week(session) + 1):
        # Monday to Friday, because a UNSW term's teaching ends on a Friday
        for weekday in calendars.WEEKDAY_NAMES[:5]:
            day = calendars.week_date(session, week, weekday, "12:00").date()
            assert day not in break_days
            assert not first_exam <= day <= last_exam


@pytest.mark.parametrize("session", list(calendars.SESSIONS))
def test_weeks_and_breaks_are_mondays_in_order(session):
    info = calendars.session_info(session)
    assert all(day.weekday() == 0 for day in info["weeks"] + info["breaks"])
    assert info["weeks"] == sorted(set(info["weeks"]))
    assert not set(info["weeks"]) & set(info["breaks"])
    assert info["weeks"][-1] < info["exams"][0] <= info["exams"][1]


def test_uts_exams_start_the_monday_after_the_final_stuvac():
    for session in ["AUT2026", "SPR2026", "AUT2027", "SPR2027"]:
        info = calendars.session_info(session)
        assert info["exams"][0] == info["breaks"][1] + timedelta(weeks=1)


# ---------- sessions that have finished ----------


def test_open_sessions_leave_out_the_finished_ones():
    # 16 Nov 2026: UTS Autumn 2026 is over, and Spring 2026 exams run until 20 Nov
    still_open = calendars.open_sessions(date(2026, 11, 16))
    assert "AUT2026" not in still_open
    assert "SPR2026" in still_open
    assert list(still_open) == [code for code in calendars.SESSIONS if code != "AUT2026"]


def test_a_session_stays_open_on_its_last_exam_day_and_closes_the_day_after():
    assert "SPR2026" in calendars.open_sessions(date(2026, 11, 20))
    assert "SPR2026" not in calendars.open_sessions(date(2026, 11, 21))


def test_no_university_has_run_out_while_a_2027_session_is_still_to_come():
    assert calendars.finished_universities(date(2026, 11, 16)) == []
    assert calendars.finished_universities(date(2027, 11, 19)) == []


def test_universities_with_no_session_left_are_named():
    # UTS Spring 2027 exams end on 19 Nov, Macquarie on 26 Nov, USyd on 27 Nov and UNSW on 9 Dec
    assert calendars.finished_universities(date(2027, 11, 20)) == ["UTS"]
    assert calendars.finished_universities(date(2027, 11, 28)) == ["UTS", "USyd", "Macquarie"]
    assert calendars.finished_universities(date(2027, 12, 10)) == ["UTS", "UNSW", "USyd", "Macquarie"]
    assert calendars.open_sessions(date(2027, 12, 10)) == {}


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
        ("AUT2027", 9, "friday", "23:59", datetime(2027, 4, 23, 23, 59)),  # the first week after StuVac
        ("UNSW_T1_2027", 7, "friday", "17:00", datetime(2027, 4, 2, 17, 0)),  # the week after flexibility week
        ("UNSW_T3_2027", 10, "friday", "23:59", datetime(2027, 11, 19, 23, 59)),  # the last day of Term 3 teaching
        ("USYD_S1_2027", 6, "monday", "09:00", datetime(2027, 4, 5, 9, 0)),  # the first day after the break
        ("USYD_S1_2027", 13, "sunday", "23:59", datetime(2027, 5, 30, 23, 59)),  # the last day of teaching
        ("MQ_S1_2027", 7, "friday", "23:59", datetime(2027, 4, 9, 23, 59)),  # the last Friday before the recess
        ("MQ_S1_2027", 8, "monday", "09:00", datetime(2027, 4, 26, 9, 0)),  # the first day after the recess
        ("MQ_S2_2027", 13, "sunday", "23:59", datetime(2027, 11, 7, 23, 59)),
    ],
)
def test_week_date(session, week, weekday, time, expected):
    assert calendars.week_date(session, week, weekday, time) == expected


# ---------- teaching_weeks ----------


def test_teaching_weeks_skip_spring_stuvac():
    assert calendars.teaching_weeks("SPR2026", 7, 10) == [
        (7, date(2026, 9, 7)),
        (8, date(2026, 9, 14)),
        # 21 Sep is StuVac, so it is not here
        (9, date(2026, 9, 28)),
        (10, date(2026, 10, 5)),
    ]


def test_teaching_weeks_skip_autumn_stuvac():
    assert calendars.teaching_weeks("AUT2026", 6, 9) == [
        (6, date(2026, 3, 23)),
        (7, date(2026, 3, 30)),
        # 6 Apr is StuVac, so it is not here
        (8, date(2026, 4, 13)),
        (9, date(2026, 4, 20)),
    ]


def test_teaching_weeks_skip_the_macquarie_recess():
    assert calendars.teaching_weeks("MQ_S1_2027", 7, 8) == [
        (7, d(5, 4)),
        # 12 and 19 Apr are the recess, so they are not here
        (8, d(26, 4)),
    ]


def test_teaching_weeks_keep_unsw_flexibility_week():
    # Week 6 keeps its number at UNSW, so it stays in the list
    assert calendars.teaching_weeks("UNSW_T1_2027", 5, 7) == [(5, d(15, 3)), (6, d(22, 3)), (7, d(29, 3))]


def test_teaching_weeks_one_week_and_all_weeks():
    assert calendars.teaching_weeks("SPR2026", 4, 4) == [(4, date(2026, 8, 17))]
    assert calendars.teaching_weeks("SPR2026", 1, 12) == list(enumerate(WEEKS["SPR2026"], 1))
    assert calendars.teaching_weeks("USYD_S2_2027", 1, 13) == list(enumerate(WEEKS["USYD_S2_2027"], 1))


@pytest.mark.parametrize("first, last", [(5, 4), (0, 3), (10, 13), (12, 1)])
def test_teaching_weeks_refuses_bad_ranges(first, last):
    with pytest.raises(ValueError):
        calendars.teaching_weeks("SPR2026", first, last)


# ---------- bad input ----------


@pytest.mark.parametrize("session", ["SUM2026", "spr2026", "AUT2025", "", "Spring 2026", "UNSW_T4_2027", "T1_2027"])
def test_unknown_session_is_a_clear_error(session):
    with pytest.raises(ValueError, match="Unknown session"):
        calendars.session_info(session)
    with pytest.raises(ValueError, match="Unknown session"):
        calendars.week_start(session, 1)
    with pytest.raises(ValueError, match="Unknown session"):
        calendars.week_date(session, 1, "friday", "23:59")
    with pytest.raises(ValueError, match="Unknown session"):
        calendars.teaching_weeks(session, 1, 2)
    with pytest.raises(ValueError, match="Unknown session"):
        calendars.last_week(session)


@pytest.mark.parametrize("week", [0, 13, -1, 100, 5.0, True, None, "5"])
def test_week_outside_1_to_12_is_a_clear_error_at_uts(week):
    with pytest.raises(ValueError, match="not a teaching week"):
        calendars.week_start("SPR2026", week)
    with pytest.raises(ValueError, match="not a teaching week"):
        calendars.week_date("SPR2026", week, "friday", "23:59")


@pytest.mark.parametrize(
    "session, week, last",
    [("UNSW_T1_2027", 11, 10), ("UNSW_T3_2027", 12, 10), ("USYD_S1_2027", 14, 13), ("MQ_S2_2027", 14, 13), ("AUT2027", 13, 12)],
)
def test_the_week_error_names_the_sessions_own_last_week(session, week, last):
    with pytest.raises(ValueError, match=f"Teaching weeks run from 1 to {last}"):
        calendars.week_start(session, week)


def test_week_13_is_real_at_usyd_and_macquarie_but_not_at_uts_or_unsw():
    assert calendars.week_start("USYD_S1_2027", 13) == d(24, 5)
    assert calendars.week_start("MQ_S1_2027", 13) == d(31, 5)
    for session in ["AUT2027", "UNSW_T1_2027"]:
        with pytest.raises(ValueError):
            calendars.week_start(session, 13)


@pytest.mark.parametrize("weekday", ["Friday", "fri", "", "funday", None])
def test_bad_weekday_is_a_clear_error(weekday):
    with pytest.raises(ValueError, match="weekday"):
        calendars.week_date("SPR2026", 3, weekday, "23:59")


@pytest.mark.parametrize("time", ["24:00", "9:00", "12:60", "noon", "", "5pm", "23:59:00"])
def test_bad_time_is_a_clear_error(time):
    with pytest.raises(ValueError, match="HH:MM"):
        calendars.week_date("SPR2026", 3, "friday", time)


# ---------- public holidays ----------


@pytest.mark.parametrize(
    "day, name",
    [
        # Copied from the NSW Government's "NSW public holidays 2026 to 2027" table
        (date(2026, 1, 1), "New Year's Day"),
        (date(2026, 1, 26), "Australia Day"),
        (date(2026, 4, 3), "Good Friday"),
        (date(2026, 4, 4), "Easter Saturday"),
        (date(2026, 4, 5), "Easter Sunday"),
        (date(2026, 4, 6), "Easter Monday"),
        (date(2026, 4, 25), "Anzac Day"),
        (date(2026, 4, 27), "the extra Anzac Day holiday"),
        (date(2026, 6, 8), "the King's Birthday"),
        (date(2026, 10, 5), "Labour Day"),
        (date(2026, 12, 25), "Christmas Day"),
        (date(2026, 12, 26), "Boxing Day"),
        (date(2026, 12, 28), "the extra Boxing Day holiday"),
        (date(2027, 1, 1), "New Year's Day"),
        (date(2027, 1, 26), "Australia Day"),
        (date(2027, 3, 26), "Good Friday"),
        (date(2027, 3, 27), "Easter Saturday"),
        (date(2027, 3, 28), "Easter Sunday"),
        (date(2027, 3, 29), "Easter Monday"),
        (date(2027, 4, 25), "Anzac Day"),
        (date(2027, 4, 26), "the extra Anzac Day holiday"),
        (date(2027, 6, 14), "the King's Birthday"),
        (date(2027, 10, 4), "Labour Day"),
        (date(2027, 12, 25), "Christmas Day"),
        (date(2027, 12, 26), "Boxing Day"),
        (date(2027, 12, 27), "the extra Christmas Day holiday"),
        (date(2027, 12, 28), "the extra Boxing Day holiday"),
    ],
)
def test_public_holidays(day, name):
    assert calendars.is_public_holiday(day)
    assert calendars.PUBLIC_HOLIDAYS[day] == name


def test_no_other_day_is_listed_as_a_public_holiday():
    assert len(calendars.PUBLIC_HOLIDAYS) == 27


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 8, 3),  # the Bank Holiday is only for banks
        date(2027, 8, 2),  # the 2027 Bank Holiday
        date(2026, 10, 6),
        date(2026, 4, 2),
        date(2026, 4, 26),
        date(2026, 9, 11),
        date(2027, 4, 27),
    ],
)
def test_ordinary_days_are_not_public_holidays(day):
    assert not calendars.is_public_holiday(day)
