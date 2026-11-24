"""Tests for due dates given as week numbers, like "friday week 7".

The student chooses their university session once (tools.choose_session, or
the picker on the home page), and from then on "friday week 7 5pm" means the
Friday of teaching week 7 in that session. The breaks with no week number
(UTS's StuVac, NUS's recess week) are skipped, because week 7 comes from the
session's own list of teaching weeks.

Every expected date below was worked out by hand from the session's official
calendar (see calendars.py), not by calling the code being tested.
No API key and no internet needed. The clock is frozen at Thursday 5 Nov 2026.
"""

import json
from datetime import date, datetime

import pytest

from deadline_agent import agent, calendars, tools

NOW = datetime(2026, 11, 5, 10, 0)  # Thursday 5 Nov 2026, 10:00 AM


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary folder and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def choose(session):
    result = tools.choose_session(session)
    assert result["status"] == "success", result["message"]
    return result


def add(due_date, title="Task"):
    return tools.add_deadline(title, due_date)


def saved(due_date):
    result = add(due_date)
    assert result["status"] == "success", result["message"]
    return result["deadline"]["due_date"]


# ---------- the dates, NUS AY2026/27 Semester 2 ----------
# Weeks 1 to 6 start 11 Jan to 15 Feb 2027, recess week is 22 Feb,
# and weeks 7 to 13 start 1 Mar to 12 Apr 2027.


@pytest.mark.parametrize(
    "words, expected",
    [
        ("friday week 7 5pm", "2027-03-05 17:00"),  # week 7 comes after recess week
        ("friday of week 7 5pm", "2027-03-05 17:00"),
        ("week 7 friday 5pm", "2027-03-05 17:00"),
        ("5pm friday week 7", "2027-03-05 17:00"),
        ("fri wk 7 17:00", "2027-03-05 17:00"),
        ("due friday, week 7 at 5pm", "2027-03-05 17:00"),
        ("Friday Week 7", "2027-03-05"),
        ("monday week 1", "2027-01-11"),
        ("sunday week 1", "2027-01-17"),
        ("wednesday week 6", "2027-02-17"),  # the week before recess week
        ("monday of week 11", "2027-03-29"),
        ("tues week 12 noon", "2027-04-06 12:00"),
        ("thurs week 13 9am", "2027-04-15 09:00"),
        ("sunday week 13 11:59pm", "2027-04-18 23:59"),
        ("sun wk9", "2027-03-21"),
    ],
)
def test_week_words_give_the_right_nus_date(words, expected):
    choose("NUS_AY2627_S2")
    assert saved(words) == expected


def test_other_universities_count_their_own_weeks():
    # UTS Autumn 2027: week 8 starts 5 Apr, StuVac is 12 Apr, week 9 starts 19 Apr
    choose("AUT2027")
    assert saved("friday week 8") == "2027-04-09"
    assert tools.add_deadline("Second", "friday week 9")["deadline"]["due_date"] == "2027-04-23"
    # UNSW Term 1 2027: week 1 starts 15 Feb
    choose("UNSW_T1_2027")
    assert tools.add_deadline("Third", "monday week 1")["deadline"]["due_date"] == "2027-02-15"
    # Macquarie Session 1 2027: week 7 starts 5 Apr, then two break weeks, week 8 starts 26 Apr
    choose("MQ_S1_2027")
    assert tools.add_deadline("Fourth", "monday week 8")["deadline"]["due_date"] == "2027-04-26"
    # SMU AY2026/27 Term 2: 14 weeks in a row from 11 Jan, recess week is week 8 (1 Mar)
    choose("SMU_AY2627_T2")
    assert tools.add_deadline("Fifth", "monday week 8")["deadline"]["due_date"] == "2027-03-01"


def test_week_dates_also_work_when_editing():
    choose("NUS_AY2627_S2")
    add("20 dec")
    result = tools.edit_deadline("Task", new_due_date="friday week 7 5pm")
    assert result["status"] == "success", result["message"]
    assert result["deadline"]["due_date"] == "2027-03-05 17:00"
    assert "That's week 7 of NUS AY2026/27 Semester 2" in result["message"]


# ---------- what the message says ----------


def test_message_names_the_week_and_the_session():
    choose("NUS_AY2627_S2")
    message = add("friday week 7 5pm")["message"]
    assert message.startswith("Saved 'Task', due Friday 5 Mar 2027, 5:00 PM. That's in 2027, not this year.")
    assert "That's week 7 of NUS AY2026/27 Semester 2 (Jan to May 2027)." in message
    assert "Friday was assumed" not in message


@pytest.mark.parametrize("words", ["week 9", "wk9", "of week 9", "week 9 5pm", "due week 9 at 11:59pm"])
def test_groot_asks_which_day_instead_of_guessing(words):
    # Some subjects are due on Friday, others on Sunday, so a guess could make reminders come late.
    # NUS week 9 starts Monday 15 Mar 2027.
    choose("NUS_AY2627_S2")
    result = add(words)
    assert result["status"] == "error"
    assert result["message"] == (
        "Which day of week 9 is it due? Week 9 runs from Monday 15 Mar to Sunday 21 Mar 2027. "
        "Type the day too, like 'friday week 9' or 'sunday week 9 11:59pm'."
    )
    assert not tools.list_deadlines()["deadlines"]


def test_message_warns_about_a_quiet_week():
    choose("SMU_AY2627_T2")
    message = add("friday week 8")["message"]
    assert "Week 8 is SMU's recess week, when most classes do not run, so check this date." in message


def test_message_warns_about_a_singapore_public_holiday():
    choose("NUS_AY2627_S2")
    # Friday of week 10 is Good Friday, 26 Mar 2027
    message = add("friday week 10")["message"]
    assert "Friday 26 Mar 2027 is a Singapore public holiday (Good Friday), so check this date." in message
    # Wednesday of week 8 is Hari Raya Puasa, 10 Mar 2027
    message = tools.add_deadline("Second", "wednesday week 8")["message"]
    assert "Wednesday 10 Mar 2027 is a Singapore public holiday (Hari Raya Puasa)" in message


def test_message_warns_about_a_nsw_public_holiday():
    choose("AUT2027")
    # UTS week 10 starts Monday 26 Apr 2027, the extra Anzac Day holiday (Anzac Day is a Sunday)
    message = add("monday week 10")["message"]
    assert "Monday 26 Apr 2027 is a NSW public holiday (the extra Anzac Day holiday)" in message


def test_ordinary_dates_get_no_week_note():
    choose("NUS_AY2627_S2")
    message = add("5 mar 2027 5pm")["message"]
    assert message == "Saved 'Task', due Friday 5 Mar 2027, 5:00 PM. That's in 2027, not this year."


# ---------- clear errors ----------


def test_week_words_without_a_chosen_session_explain_what_to_do():
    result = add("friday week 7")
    assert result["status"] == "error"
    assert "first choose your university and session on Groot's home page" in result["message"]
    assert not tools.list_deadlines()["deadlines"]


def test_a_week_the_session_does_not_have_is_refused():
    choose("NUS_AY2627_S2")
    result = add("friday week 14")
    assert result["status"] == "error"
    assert result["message"] == "NUS AY2026/27 Semester 2 (Jan to May 2027) has weeks 1 to 13, so there is no week 14."
    assert add("week 0")["status"] == "error"


def test_smu_exam_weeks_point_to_the_exam_timetable():
    choose("SMU_AY2627_T2")
    message = add("friday week 15")["message"]
    assert "has weeks 1 to 14, so there is no week 15." in message
    assert "That week is in the exam period, so check the exam timetable for the date." in message


def test_the_exam_hint_is_only_for_sessions_with_numbered_exam_weeks():
    choose("NUS_AY2627_S2")
    assert "exam period" not in add("week 14")["message"]


def test_a_word_that_is_not_a_day_is_refused():
    choose("NUS_AY2627_S2")
    result = add("payday week 7")
    assert result["status"] == "error"
    assert "'payday' is not a day of the week" in result["message"]


def test_the_day_given_twice_is_refused():
    choose("NUS_AY2627_S2")
    result = add("friday week 7 monday")
    assert result["status"] == "error"
    assert "Give the day once" in result["message"]


def test_a_week_already_past_is_refused(monkeypatch):
    choose("NUS_AY2627_S2")
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 10, 9, 0))  # Wednesday of week 8
    result = add("friday week 7")
    assert result["status"] == "error"
    assert result["message"] == (
        "'friday week 7' would be Friday 5 Mar 2027, 11:59 PM, which is already in the past. Please check the date "
        'and time. To plan ahead, choose your next session under "Week numbers count in" on the home page.'
    )


def test_an_ordinary_past_date_gets_no_session_hint(monkeypatch):
    choose("NUS_AY2627_S2")
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 10, 10, 0))
    result = tools.add_deadline("Old", "9am")  # 9 AM today, an hour ago
    assert result["status"] == "error" and "Week numbers count in" not in result["message"]


@pytest.mark.parametrize("words", ["in 2 weeks", "end of next week", "in a week", "end of the week"])
def test_other_week_phrases_still_work_without_a_session(words):
    # These never needed a session, and must not be mistaken for week numbers
    assert add(words)["status"] == "success"


# ---------- choosing the session ----------


def test_choosing_saves_next_to_the_deadlines_file(deadlines_file):
    result = choose("NUS_AY2627_S2")
    assert result["message"] == (
        "Week numbers now count in NUS AY2026/27 Semester 2 (Jan to May 2027). "
        'For example, "friday week 7 5pm" works when you add a deadline.'
    )
    settings = deadlines_file.with_name("groot_settings.json")
    assert json.loads(settings.read_text(encoding="utf-8")) == {"session": "NUS_AY2627_S2"}
    assert tools._chosen_session() == "NUS_AY2627_S2"


def test_an_empty_choice_switches_week_numbers_off():
    choose("NUS_AY2627_S2")
    result = choose("")
    assert result["message"].startswith("Week numbers are switched off.")
    assert tools._chosen_session() is None
    assert add("friday week 7")["status"] == "error"


@pytest.mark.parametrize("bad", ["NOT_A_SESSION", "../deadlines", None, 7])
def test_an_unknown_session_is_refused_and_nothing_changes(bad):
    choose("NUS_AY2627_S2")
    if bad is None or bad == 7:
        # Not text, so it counts as "switch off" only if it is empty text. A number or None is treated as "".
        tools.choose_session(bad)
        assert tools._chosen_session() is None
        return
    result = tools.choose_session(bad)
    assert result["status"] == "error"
    assert tools._chosen_session() == "NUS_AY2627_S2"


@pytest.mark.parametrize("contents", ["not json", "[]", '{"session": 5}', '{"session": "GONE_2019"}', ""])
def test_a_broken_settings_file_counts_as_no_session(deadlines_file, contents):
    deadlines_file.with_name("groot_settings.json").write_text(contents, encoding="utf-8")
    assert tools._chosen_session() is None
    assert add("friday week 7")["status"] == "error"


def test_a_custom_session_works_too():
    # "My university is not listed": 12 weeks from Mon 1 Mar 2027, one break week after week 6.
    # Weeks 1 to 6 start 1 Mar to 5 Apr, the break is 12 Apr, so week 7 starts 19 Apr.
    choose("CUSTOM:2027-03-01:12:6:1")
    assert saved("friday week 7") == "2027-04-23"


# ---------- where a day falls ----------


@pytest.mark.parametrize(
    "session, day, expected",
    [
        ("NUS_AY2627_S2", date(2027, 1, 1), "before week 1"),
        ("NUS_AY2627_S2", date(2027, 1, 11), "week 1"),
        ("NUS_AY2627_S2", date(2027, 1, 17), "week 1"),
        ("NUS_AY2627_S2", date(2027, 2, 24), "a break with no week number"),  # recess week
        ("NUS_AY2627_S2", date(2027, 3, 1), "week 7"),
        ("NUS_AY2627_S2", date(2027, 4, 21), "a break with no week number"),  # reading week
        ("NUS_AY2627_S2", date(2027, 4, 28), "the exam period"),
        ("NUS_AY2627_S2", date(2027, 6, 1), "after the session"),
        ("SMU_AY2627_T2", date(2027, 3, 3), "week 8, SMU's recess week"),
        ("UNSW_T1_2027", date(2027, 3, 24), "week 6, UNSW's flexibility week"),
    ],
)
def test_where_is(session, day, expected):
    assert calendars.where_is(session, day) == expected


# ---------- what Groot's chat is told ----------


def test_chat_is_told_when_no_session_is_chosen():
    assert "No university session is chosen" in agent.week_numbers_line()


def test_chat_is_told_the_session_and_where_today_falls(monkeypatch):
    choose("NUS_AY2627_S2")
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 3, 9, 0))
    line = agent.week_numbers_line()
    assert "Week numbers count in NUS AY2026/27 Semester 2 (Jan to May 2027), and today is in week 7." in line
    assert "pass them on exactly as typed" in line
