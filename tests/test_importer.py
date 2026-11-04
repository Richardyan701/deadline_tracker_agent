"""Tests for the importer, which turns outline items into review rows and saves them.

These need no API key and no internet. Saving goes to a temporary file
(through the DEADLINES_FILE variable), so your real deadlines.json is never touched.

Spring 2026 dates used below (from the UTS calendar):
week 1 starts Mon 27 Jul, week 7 Mon 7 Sep, week 8 Mon 14 Sep, StuVac 21 to 27 Sep,
week 9 Mon 28 Sep, week 10 Mon 5 Oct (Labour Day), week 12 Mon 19 Oct.
"""

from datetime import datetime

import pytest

from deadline_agent import importer, tools

# Pretend "now" is Monday 20 Jul 2026, the week before Spring starts
NOW = datetime(2026, 7, 20, 9, 0)

TIMETABLE = {
    "33130": [
        {"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"},
        {"activity": "Lec1", "weekday": "thursday", "start": "13:00", "end": "15:00"},
    ],
    "35010": [{"activity": "Wrk1", "weekday": "wednesday", "start": "10:00", "end": "12:00"}],
    "48023": [{"activity": "Tut1", "weekday": "monday", "start": "14:00", "end": "15:30"}],
}


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary file and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def item(name, when, code="33130", subject="Mathematics 1", **fields):
    """An outline item like the outline reader returns, with nothing set but what is given."""
    found = {
        "subject_code": code, "subject_name": subject, "name": name, "task_number": None,
        "weight_percent": None, "when": when, "date": None, "week": None, "first_week": None,
        "last_week": None, "weekday": None, "time": None, "quote": "",
    }
    found.update(fields)
    return found


def event(title, due, code="33130", all_day=False):
    """A Canvas event like canvas.parse_feed returns."""
    return {"subject_code": code, "title": title, "due": due, "all_day": all_day, "uid": f"event-{title}"}


def preview(*items, session="SPR2026", now=NOW, **options):
    return importer.build_preview(list(items), session, now=now, **options)


def only_row(*items, **options):
    rows = preview(*items, **options)
    assert len(rows) == 1
    return rows[0]


# ---------- the rules table, one row at a time ----------


def test_calendar_date_with_a_time_is_exact():
    row = only_row(item("Essay", "date", date="2026-08-14", time="17:00", weight_percent=30))
    assert row == {
        "title": "33130 Essay",
        "subject": "33130 Mathematics 1",
        "weight_percent": 30,
        "due_date": "2026-08-14 17:00",
        "status": "exact",
        "source": "outline",
        "note": "The outline gives the date and time.",
        "include": True,
    }


def test_calendar_date_with_no_time_is_exact_at_1159_pm():
    row = only_row(item("Essay", "date", date="2026-08-14"))
    assert (row["due_date"], row["status"], row["include"]) == ("2026-08-14 23:59", "exact", True)
    assert "11:59 PM" in row["note"]


def test_week_and_weekday_is_exact():
    row = only_row(item("Lab report", "week", week=3, weekday="tuesday"))
    assert (row["due_date"], row["status"], row["include"]) == ("2026-08-11 23:59", "exact", True)
    assert row["note"] == "The outline says Tuesday of week 3 with no time, so 11:59 PM was used."


def test_week_weekday_and_time_is_exact():
    row = only_row(item("Lab report", "week", week=3, weekday="tuesday", time="14:00"))
    assert (row["due_date"], row["status"]) == ("2026-08-11 14:00", "exact")


def test_week_and_time_with_no_day_assumes_friday():
    # A time alone does not say which day, so the day is only assumed
    row = only_row(item("Lab report", "week", week=3, time="14:00"))
    assert (row["due_date"], row["status"], row["include"]) == ("2026-08-14 14:00", "assumed", True)
    assert "with no day, so Friday of week 3 was assumed" in row["note"]


def test_week_only_is_friday_1159_pm_assumed():
    row = only_row(item("Skills Test 1", "week", week=7))
    assert (row["due_date"], row["status"], row["include"]) == ("2026-09-11 23:59", "assumed", True)
    assert row["note"] == "The outline says week 7 with no day, so Friday of week 7 at 11:59 PM was assumed."


def test_week_after_stuvac_skips_the_stuvac_week():
    # Week 9 starts on 28 Sep, not 21 Sep (StuVac)
    assert only_row(item("Quiz", "week", week=9))["due_date"] == "2026-10-02 23:59"


def test_tutorial_in_week_n_uses_the_timetable():
    row = only_row(item("Skills Test 2", "tutorial", week=5), timetable=TIMETABLE)
    assert (row["due_date"], row["status"], row["include"]) == ("2026-08-25 09:00", "exact", True)
    assert row["note"] == (
        "The outline says your tutorial in week 5, and your timetable has your Tut1 class on Tuesday at 09:00."
    )


def test_tutorial_uses_the_workshop_when_there_is_no_tut():
    row = only_row(item("Quiz", "tutorial", week=2, code="35010", subject="Foundation Mathematics"), timetable=TIMETABLE)
    assert (row["due_date"], row["status"]) == ("2026-08-05 10:00", "exact")


def test_tut_wins_over_wrk_when_a_subject_has_both():
    classes = {"33130": [
        {"activity": "Wrk1", "weekday": "monday", "start": "08:00", "end": "10:00"},
        {"activity": "Tut1", "weekday": "thursday", "start": "12:00", "end": "13:00"},
    ]}
    row = only_row(item("Quiz", "tutorial", week=2), timetable=classes)
    assert row["due_date"] == "2026-08-06 12:00"


def test_tutorial_with_no_timetable_needs_input():
    row = only_row(item("Skills Test 2", "tutorial", week=5))
    assert (row["due_date"], row["status"], row["include"]) == (None, "needs_input", False)
    assert "please type the date" in row["note"]
    assert "Week 5 starts on Monday 24 Aug 2026" in row["note"]


def test_tutorial_when_the_timetable_has_two_tutorial_times_needs_input():
    classes = {"33130": [
        {"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"},
        {"activity": "Tut2", "weekday": "friday", "start": "09:00", "end": "11:00"},
    ]}
    row = only_row(item("Skills Test 2", "tutorial", week=5), timetable=classes)
    assert (row["due_date"], row["status"]) == (None, "needs_input")
    assert "more than one tutorial time" in row["note"]


def test_in_the_tutorials_with_no_week_is_one_row_that_needs_input():
    row = only_row(item("Skills Tests 2-5", "tutorial"), timetable=TIMETABLE)
    assert (row["title"], row["due_date"], row["status"], row["include"]) == (
        "33130 Skills Tests 2-5", None, "needs_input", False
    )


def test_each_week_from_a_to_b_is_one_row_per_teaching_week():
    rows = preview(item("Weekly quiz", "recurring", first_week=7, last_week=10, weight_percent=2))
    assert [(row["title"], row["due_date"]) for row in rows] == [
        ("33130 Weekly quiz (week 7)", "2026-09-11 23:59"),
        ("33130 Weekly quiz (week 8)", "2026-09-18 23:59"),
        # StuVac (21 to 27 Sep) is skipped
        ("33130 Weekly quiz (week 9)", "2026-10-02 23:59"),
        ("33130 Weekly quiz (week 10)", "2026-10-09 23:59"),
    ]
    assert all(row["status"] == "assumed" and row["include"] for row in rows)
    assert all(row["weight_percent"] == 2 for row in rows)


def test_each_week_with_a_day_is_exact():
    rows = preview(item("Reflection", "recurring", first_week=1, last_week=3, weekday="wednesday", time="18:00"))
    assert [row["due_date"] for row in rows] == ["2026-07-29 18:00", "2026-08-05 18:00", "2026-08-12 18:00"]
    assert all(row["status"] == "exact" for row in rows)


def test_each_week_with_no_last_week_runs_to_week_12_and_is_only_assumed():
    rows = preview(item("Reflection", "recurring", first_week=11, weekday="wednesday"))
    assert [row["due_date"] for row in rows] == ["2026-10-14 23:59", "2026-10-21 23:59"]
    assert all(row["status"] == "assumed" for row in rows)
    assert "no last week, so week 12 was used" in rows[0]["note"]


@pytest.mark.parametrize("first, last", [(None, 12), (0, 5), (4, 13), (8, 3)])
def test_each_week_with_unusable_weeks_is_unknown(first, last):
    row = only_row(item("Quiz", "recurring", first_week=first, last_week=last))
    assert (row["due_date"], row["status"], row["include"]) == (None, "unknown", False)


def test_exam_period_is_unknown_and_points_to_the_exam_timetable():
    row = only_row(item("Final exam", "exam_period", weight_percent=40))
    assert (row["due_date"], row["status"], row["include"]) == (None, "unknown", False)
    assert "check the UTS exam timetable" in row["note"]
    assert "Monday 2 Nov 2026 to Friday 20 Nov 2026" in row["note"]


def test_nothing_usable_is_unknown():
    row = only_row(item("Participation", "unknown"))
    assert (row["due_date"], row["status"], row["include"]) == (None, "unknown", False)
    assert row["note"] == importer.NO_DATE_NOTE


@pytest.mark.parametrize(
    "fields",
    [
        {"when": "date"},  # no date
        {"when": "week"},  # no week
        {"when": "week", "week": 13},  # not a teaching week
        {"when": "week", "week": 0, "weekday": "monday"},
        {"when": "tutorial", "week": 14},
    ],
)
def test_missing_or_impossible_details_are_unknown(fields):
    row = only_row(item("Quiz", **fields), timetable=TIMETABLE)
    assert (row["due_date"], row["status"], row["include"]) == (None, "unknown", False)


def test_impossible_week_note_names_the_session():
    row = only_row(item("Quiz", "week", week=13))
    assert row["note"] == (
        "The outline says week 13, but Spring 2026 only has teaching weeks 1 to 12, so the date is unknown."
    )


def test_autumn_session_uses_the_autumn_calendar():
    row = only_row(item("Quiz", "week", week=8, weekday="monday"), session="AUT2026", now=datetime(2026, 1, 5))
    assert row["due_date"] == "2026-04-13 23:59"  # the Monday after Autumn StuVac


def test_unknown_when_value_is_a_clear_error():
    with pytest.raises(ValueError, match="Unknown 'when' value 'soon'"):
        preview(item("Quiz", "soon"))


def test_unknown_session_is_a_clear_error():
    with pytest.raises(ValueError, match="Unknown session"):
        preview(item("Quiz", "week", week=3), session="SUM2026")


# ---------- past dates ----------


def test_a_date_that_has_passed_is_past_and_unticked():
    row = only_row(item("Essay", "date", date="2026-08-14"), now=datetime(2026, 9, 1, 12, 0))
    assert (row["status"], row["include"]) == ("past", False)
    assert row["due_date"] == "2026-08-14 23:59"
    assert row["note"].endswith("This date has already passed.")


def test_only_the_weeks_already_gone_are_past():
    rows = preview(item("Quiz", "recurring", first_week=1, last_week=3), now=datetime(2026, 8, 6, 9, 0))
    assert [(row["status"], row["include"]) for row in rows] == [("past", False), ("assumed", True), ("assumed", True)]


def test_later_the_same_day_is_not_past():
    row = only_row(item("Essay", "date", date="2026-08-14", time="17:00"), now=datetime(2026, 8, 14, 16, 59))
    assert row["status"] == "exact"


def test_rows_with_no_date_are_never_past():
    row = only_row(item("Final exam", "exam_period"), now=datetime(2026, 12, 31))
    assert row["status"] == "unknown"


def test_past_canvas_rows_are_past():
    rows = preview(
        canvas_events=[event("Week 1 check-in", "2026-07-31 17:00")], chosen_subjects=["33130"], now=datetime(2026, 8, 3)
    )
    assert (rows[0]["status"], rows[0]["include"]) == ("past", False)


def test_now_defaults_to_the_tools_clock(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 9, 1, 12, 0))
    rows = importer.build_preview([item("Essay", "date", date="2026-08-14")], "SPR2026")
    assert rows[0]["status"] == "past"


# ---------- public holidays ----------


def test_exact_date_on_a_public_holiday_becomes_assumed():
    # Monday of week 10 in Spring is Labour Day, 5 Oct 2026
    row = only_row(item("Assignment 2", "week", week=10, weekday="monday"))
    assert (row["due_date"], row["status"], row["include"]) == ("2026-10-05 23:59", "assumed", True)
    assert "Monday 5 Oct 2026 is a NSW public holiday (Labour Day), so check this date." in row["note"]


def test_only_the_holiday_week_of_a_weekly_item_is_flagged():
    rows = preview(item("Lab", "recurring", first_week=9, last_week=11, weekday="monday"))
    assert [row["status"] for row in rows] == ["exact", "assumed", "exact"]
    assert "Labour Day" in rows[1]["note"]
    assert "holiday" not in rows[0]["note"] + rows[2]["note"]


def test_assumed_friday_on_good_friday_stays_assumed_and_says_why():
    # Friday of Autumn week 7 is Good Friday, 3 Apr 2026
    row = only_row(item("Quiz", "week", week=7), session="AUT2026", now=datetime(2026, 1, 5))
    assert (row["due_date"], row["status"]) == ("2026-04-03 23:59", "assumed")
    assert "(Good Friday)" in row["note"]


def test_the_extra_anzac_day_holiday_is_flagged():
    row = only_row(item("Quiz", "week", week=10, weekday="monday"), session="AUT2026", now=datetime(2026, 1, 5))
    assert (row["due_date"], row["status"]) == ("2026-04-27 23:59", "assumed")
    assert "the extra Anzac Day holiday" in row["note"]


def test_canvas_date_on_a_public_holiday_becomes_assumed():
    rows = preview(canvas_events=[event("Lab 4", "2026-10-05 17:00")], chosen_subjects=["33130"])
    assert (rows[0]["status"], rows[0]["include"]) == ("assumed", True)
    assert "Labour Day" in rows[0]["note"]


def test_a_past_holiday_row_is_past():
    row = only_row(item("Lab", "week", week=10, weekday="monday"), now=datetime(2026, 10, 10))
    assert row["status"] == "past"
    assert "Labour Day" in row["note"]


# ---------- which subjects are used ----------


def test_subjects_without_an_outline_are_ignored():
    rows = preview(
        item("Skills Test 2", "tutorial", week=5),
        timetable=TIMETABLE,
        canvas_events=[event("Lab 1", "2026-08-07 23:59", code="48023")],
    )
    assert [row["title"] for row in rows] == ["33130 Skills Test 2"]
    assert all("48023" not in str(row) for row in rows)


def test_chosen_subjects_leaves_out_other_outlines():
    rows = preview(
        item("Skills Test 1", "week", week=2),
        item("Project", "week", week=6, code="48023", subject="Programming Fundamentals"),
        chosen_subjects=["33130"],
    )
    assert [row["title"] for row in rows] == ["33130 Skills Test 1"]


def test_chosen_subject_with_only_canvas_events():
    rows = preview(canvas_events=[event("Group plan", "2026-08-21 23:59", code="31250")], chosen_subjects=["31250"])
    assert (rows[0]["title"], rows[0]["subject"], rows[0]["source"]) == ("31250 Group plan", "31250", "canvas")


def test_canvas_events_with_no_course_code_are_ignored():
    rows = preview(item("Essay", "week", week=3), canvas_events=[event("Dentist", "2026-08-12 10:00", code="")])
    assert [row["title"] for row in rows] == ["33130 Essay"]


# ---------- matching Canvas events ----------


def test_clear_match_takes_the_canvas_date_even_when_it_moved():
    rows = preview(
        item("Skills Test 1", "week", week=7, weight_percent=10),
        canvas_events=[event("Skills Test 1", "2026-09-14 17:00")],
    )
    assert rows == [{
        "title": "33130 Skills Test 1",
        "subject": "33130 Mathematics 1",
        "weight_percent": 10,
        "due_date": "2026-09-14 17:00",
        "status": "exact",
        "source": "both",
        "note": "The date comes from Canvas. The outline suggested Friday 11 Sep 2026, 11:59 PM.",
        "include": True,
    }]


def test_match_with_the_same_date_says_so():
    rows = preview(item("Essay", "week", week=3), canvas_events=[event("Essay", "2026-08-14 23:59")])
    assert rows[0]["note"] == "The date comes from Canvas and matches the outline."


def test_match_ignores_case_and_punctuation():
    rows = preview(item("Skills Test 1", "week", week=7), canvas_events=[event("SKILLS TEST 1!", "2026-09-10 12:00")])
    assert (len(rows), rows[0]["source"], rows[0]["due_date"]) == (1, "both", "2026-09-10 12:00")


def test_match_with_extra_words_in_canvas():
    rows = preview(
        item("Assignment 2", "week", week=8),
        canvas_events=[event("Assignment 2: Data Report", "2026-09-18 17:00")],
    )
    assert (len(rows), rows[0]["source"]) == (1, "both")


def test_numbers_pick_the_right_test_among_similar_names():
    items = [item(f"Skills Test {number}", "week", week=number + 1) for number in (1, 2, 3)]
    rows = preview(*items, canvas_events=[event("Skills Test 2", "2026-08-12 10:00")])
    assert [(row["title"], row["source"]) for row in rows] == [
        ("33130 Skills Test 1", "outline"),
        ("33130 Skills Test 2", "both"),
        ("33130 Skills Test 3", "outline"),
    ]
    assert rows[1]["due_date"] == "2026-08-12 10:00"


def test_task_number_counts_when_the_name_has_no_number():
    rows = preview(
        item("Data Analysis Report", "week", week=9, task_number=2),
        canvas_events=[event("Assessment 2 Data Analysis Report", "2026-10-01 23:59")],
    )
    assert (len(rows), rows[0]["source"]) == (1, "both")


def test_different_numbers_never_match():
    rows = preview(
        item("Data Analysis Report", "week", week=9, task_number=2),
        canvas_events=[event("Assessment 3 Data Analysis Report", "2026-10-20 23:59")],
    )
    assert [row["source"] for row in rows] == ["outline", "canvas"]
    assert rows[1]["note"] == "Only Canvas lists this."


def test_names_that_are_not_alike_do_not_match():
    rows = preview(item("Quiz 1", "week", week=4), canvas_events=[event("Assignment 1", "2026-08-21 23:59")])
    assert [row["source"] for row in rows] == ["outline", "canvas"]


def test_a_near_tie_is_not_merged_and_both_sides_are_flagged():
    rows = preview(
        item("Reflection", "week", week=4),
        item("Reflections", "week", week=6),
        canvas_events=[event("Reflection", "2026-08-20 23:59")],
    )
    assert [row["source"] for row in rows] == ["outline", "outline", "canvas"]
    assert [row["due_date"] for row in rows] == ["2026-08-21 23:59", "2026-09-04 23:59", "2026-08-20 23:59"]
    assert all("check for a duplicate" in row["note"].lower() for row in rows)
    assert rows[2]["note"].startswith("Canvas lists this, and it might be an outline row too")


def test_weekly_rows_with_the_same_name_are_never_merged():
    rows = preview(
        item("Weekly quiz", "recurring", first_week=7, last_week=8),
        canvas_events=[event("Weekly quiz", "2026-09-11 23:59")],
    )
    assert [row["source"] for row in rows] == ["outline", "outline", "canvas"]
    assert rows[0]["due_date"] == "2026-09-11 23:59"  # the outline row keeps its own date


def test_two_events_that_pick_the_same_row_are_not_merged():
    rows = preview(
        item("Essay", "week", week=6),
        canvas_events=[event("Essay", "2026-09-03 23:59"), event("Essay draft", "2026-08-20 23:59")],
    )
    assert [row["source"] for row in rows] == ["outline", "canvas", "canvas"]
    assert rows[0]["due_date"] == "2026-09-04 23:59"
    assert all("check for a duplicate" in row["note"].lower() for row in rows)


def test_an_event_in_another_subject_never_matches():
    rows = preview(
        item("Skills Test 1", "week", week=2),
        item("Skills Test 1", "week", week=3, code="35010", subject="Foundation Mathematics"),
        canvas_events=[event("Skills Test 1", "2026-08-12 10:00", code="35010")],
    )
    assert [(row["title"], row["source"]) for row in rows] == [
        ("33130 Skills Test 1", "outline"),
        ("35010 Skills Test 1", "both"),
    ]


def test_canvas_gives_a_date_to_an_outline_item_that_had_none():
    rows = preview(item("Final exam", "exam_period"), canvas_events=[event("Final Exam", "2026-11-09 09:00")])
    assert (len(rows), rows[0]["due_date"], rows[0]["status"], rows[0]["source"], rows[0]["include"]) == (
        1, "2026-11-09 09:00", "exact", "both", True
    )
    assert rows[0]["note"] == "The date comes from Canvas, because the outline did not give one."


def test_canvas_only_event_becomes_its_own_exact_row():
    rows = preview(item("Essay", "week", week=3), canvas_events=[event("Field trip form", "2026-08-07 17:00")])
    assert rows[1] == {
        "title": "33130 Field trip form",
        "subject": "33130 Mathematics 1",
        "weight_percent": None,
        "due_date": "2026-08-07 17:00",
        "status": "exact",
        "source": "canvas",
        "note": "Only Canvas lists this.",
        "include": True,
    }


def test_all_day_canvas_events_say_so():
    rows = preview(
        item("Essay", "week", week=3),
        canvas_events=[
            event("Essay", "2026-08-13 23:59", all_day=True),
            event("Excursion", "2026-08-20 23:59", all_day=True),
        ],
    )
    assert all("all-day event, so 11:59 PM was used" in row["note"] for row in rows)


# ---------- the whole table ----------


def test_include_starts_ticked_only_for_exact_and_assumed():
    rows = preview(
        item("A", "date", date="2026-08-14"),  # exact
        item("B", "week", week=4),  # assumed
        item("C", "tutorial"),  # needs_input
        item("D", "unknown"),  # unknown
        item("E", "date", date="2026-07-01"),  # past
    )
    assert [(row["status"], row["include"]) for row in rows] == [
        ("exact", True), ("assumed", True), ("needs_input", False), ("unknown", False), ("past", False),
    ]


def test_build_preview_saves_nothing(deadlines_file):
    preview(item("Essay", "week", week=3), canvas_events=[event("Quiz", "2026-08-07 17:00")])
    assert not deadlines_file.exists()


# ---------- save_rows ----------


def test_save_rows_saves_each_row_and_returns_one_result_each():
    rows = preview(item("Essay", "week", week=3), item("Quiz", "date", date="2026-08-20", time="10:00"))
    results = importer.save_rows(rows)

    assert [result["status"] for result in results] == ["success", "success"]
    assert tools.list_deadlines()["deadlines"] == [
        {"title": "33130 Essay", "due_date": "2026-08-14 23:59", "subject": "33130 Mathematics 1", "done": False},
        {"title": "33130 Quiz", "due_date": "2026-08-20 10:00", "subject": "33130 Mathematics 1", "done": False},
    ]


def test_a_typed_date_for_a_needs_input_row_is_saved():
    row = only_row(item("Skills Test 2", "tutorial", week=5))
    row["due_date"] = "2026-08-25 09:00"
    assert importer.save_rows([row])[0]["status"] == "success"


def test_one_bad_row_does_not_stop_the_others():
    rows = preview(item("Final exam", "exam_period"), item("Essay", "week", week=3), item("Essay", "week", week=4))
    rows.append({**rows[1], "title": "33130 Old quiz", "due_date": "2026-07-01 10:00"})
    results = importer.save_rows(rows)

    assert [result["status"] for result in results] == ["error", "success", "error", "error"]
    assert "when it is due" in results[0]["message"]  # no date
    assert "already have a deadline called '33130 Essay'" in results[2]["message"]  # the same title twice
    assert "already in the past" in results[3]["message"]
    assert [d["title"] for d in tools.list_deadlines()["deadlines"]] == ["33130 Essay"]


def test_save_rows_with_no_rows():
    assert importer.save_rows([]) == []
