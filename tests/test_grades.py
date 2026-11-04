"""Tests for the "What do I need?" grade calculator.

Covers the optional weight_percent and mark_percent fields, add_deadline's
weight, set_mark, grade_needed and its maths, old files without the new
fields, and the outline drop box passing weights through. No API key and
no internet needed.
"""

import json
from datetime import datetime

import pytest

from deadline_agent import importer, tools

# Pretend "now" is Thursday 5 Nov 2026, 10:00 AM in Sydney
NOW = datetime(2026, 11, 5, 10, 0)

SUBJECT = "41039 Programming Fundamentals"


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Point the tools at a fresh temporary file and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


def save(path, *items):
    """Write deadlines straight to the file. Each item is (title, weight, mark), all in SUBJECT.

    weight or mark can be None, and then that field is left out, like an old file.
    """
    rows = []
    for title, weight, mark in items:
        row = {"title": title, "due_date": "2026-11-20", "subject": SUBJECT, "done": mark is not None}
        if weight is not None:
            row["weight_percent"] = weight
        if mark is not None:
            row["mark_percent"] = mark
        rows.append(row)
    path.write_text(json.dumps(rows), encoding="utf-8")


def bands(result):
    """Each band as (result, needed_average)."""
    return {key: (band["result"], band["needed_average"]) for key, band in result["bands"].items()}


# ---------- old files and the new fields ----------


OLD_FILE = [
    {"title": "Essay", "due_date": "2026-11-20", "subject": "Writing", "done": False},
    {"title": "Quiz", "due_date": "2026-11-13 17:00", "subject": "", "done": True},
]


def test_an_old_file_without_the_new_fields_still_loads(deadlines_file):
    deadlines_file.write_text(json.dumps(OLD_FILE, indent=2), encoding="utf-8")

    assert tools.list_deadlines()["deadlines"] == [OLD_FILE[1], OLD_FILE[0]]  # soonest first


def test_an_old_file_saves_without_gaining_new_fields(deadlines_file):
    deadlines_file.write_text(json.dumps(OLD_FILE, indent=2), encoding="utf-8")

    tools.add_deadline("Report", "friday")  # any save rewrites the whole file

    saved = json.loads(deadlines_file.read_text(encoding="utf-8"))
    assert saved[:2] == OLD_FILE  # exactly the same, no weight_percent or mark_percent added
    assert saved[2] == {"title": "Report", "due_date": "2026-11-06", "subject": "", "done": False}
    assert not list(deadlines_file.parent.glob("*.corrupt-*"))  # it was not treated as broken


def test_null_weight_and_mark_are_fine(deadlines_file):
    rows = [{**OLD_FILE[0], "weight_percent": None, "mark_percent": None}]
    deadlines_file.write_text(json.dumps(rows), encoding="utf-8")
    assert tools.list_deadlines()["deadlines"] == rows


@pytest.mark.parametrize("bad", [-1, 101, "30", True, [30]])
def test_a_bad_weight_in_the_file_makes_it_unreadable(deadlines_file, bad):
    # The same rule as any other broken field: treated as empty, and backed up on the next save
    deadlines_file.write_text(json.dumps([{**OLD_FILE[0], "weight_percent": bad}]), encoding="utf-8")
    assert tools.list_deadlines()["deadlines"] == []


# ---------- add_deadline's weight ----------


def test_add_deadline_saves_a_weight(deadlines_file):
    result = tools.add_deadline("Exam", "20 nov", SUBJECT, 50)

    assert result["status"] == "success"
    assert result["deadline"]["weight_percent"] == 50
    assert json.loads(deadlines_file.read_text())[0]["weight_percent"] == 50


@pytest.mark.parametrize("given, saved", [(30.0, 30), ("30%", 30), (" 12.5 ", 12.5), (0, 0), (100, 100)])
def test_add_deadline_tidies_the_weight(given, saved):
    assert tools.add_deadline("Exam", "20 nov", SUBJECT, given)["deadline"]["weight_percent"] == saved


def test_add_deadline_without_a_weight_has_no_weight_field():
    assert "weight_percent" not in tools.add_deadline("Exam", "20 nov")["deadline"]


@pytest.mark.parametrize("bad", [-5, 100.5, "lots", True, float("nan"), float("inf")])
def test_add_deadline_refuses_a_bad_weight_and_saves_nothing(deadlines_file, bad):
    result = tools.add_deadline("Exam", "20 nov", SUBJECT, bad)

    assert result["status"] == "error"
    assert "weight_percent must be a number from 0 to 100" in result["message"]
    assert not deadlines_file.exists()


# ---------- set_mark ----------


def test_set_mark_saves_the_mark_and_marks_it_done(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, None))

    result = tools.set_mark("quiz 1", 78)

    assert result == {
        "status": "success",
        "message": "Set your mark to 78% for 'Quiz 1'. It is marked as done too.",
        "deadline": {
            "title": "Quiz 1", "due_date": "2026-11-20", "subject": SUBJECT, "done": True,
            "weight_percent": 10, "mark_percent": 78,
        },
    }
    assert json.loads(deadlines_file.read_text())[0]["mark_percent"] == 78


def test_set_mark_can_change_only_the_weight(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, None))

    result = tools.set_mark("Quiz 1", weight_percent=15)

    assert result["message"] == "Set its weight to 15% for 'Quiz 1'."
    assert result["deadline"]["weight_percent"] == 15
    assert result["deadline"]["done"] is False  # no mark, so not finished
    assert "mark_percent" not in result["deadline"]


def test_set_mark_can_set_both(deadlines_file):
    save(deadlines_file, ("Quiz 1", None, None))

    result = tools.set_mark("Quiz 1", 80, 20)

    assert result["message"] == "Set your mark to 80% and its weight to 20% for 'Quiz 1'. It is marked as done too."
    assert (result["deadline"]["weight_percent"], result["deadline"]["mark_percent"]) == (20, 80)


def test_set_mark_can_change_a_mark(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, 50))
    assert tools.set_mark("Quiz 1", 65)["deadline"]["mark_percent"] == 65


@pytest.mark.parametrize("mark", [0, 100])
def test_marks_of_0_and_100_are_allowed(deadlines_file, mark):
    save(deadlines_file, ("Quiz 1", 10, None))
    assert tools.set_mark("Quiz 1", mark)["deadline"]["mark_percent"] == mark


def test_set_mark_for_a_missing_deadline(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, None))
    before = deadlines_file.read_bytes()

    result = tools.set_mark("Quiz 9", 50)

    assert result["status"] == "error"
    assert "couldn't find a deadline called 'Quiz 9'" in result["message"]
    assert deadlines_file.read_bytes() == before


def test_set_mark_needs_a_mark_or_a_weight(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, None))

    for result in (tools.set_mark("Quiz 1"), tools.set_mark("Quiz 1", "", "")):
        assert result == {"status": "error", "message": "Tell me the mark (0 to 100), the weight (0 to 100) or both."}


@pytest.mark.parametrize("mark", [-1, 101, "great", False, float("nan")])
def test_set_mark_refuses_a_bad_mark(deadlines_file, mark):
    save(deadlines_file, ("Quiz 1", 10, None))
    before = deadlines_file.read_bytes()

    result = tools.set_mark("Quiz 1", mark)

    assert result["status"] == "error"
    assert "mark_percent must be a number from 0 to 100" in result["message"]
    assert deadlines_file.read_bytes() == before


def test_set_mark_refuses_a_bad_weight(deadlines_file):
    save(deadlines_file, ("Quiz 1", 10, None))
    assert "weight_percent must be a number from 0 to 100" in tools.set_mark("Quiz 1", 50, 120)["message"]


def test_set_mark_refuses_a_title_that_is_not_text():
    assert tools.set_mark(42, 50)["status"] == "error"


def test_set_mark_when_the_file_cannot_be_saved(deadlines_file, monkeypatch):
    save(deadlines_file, ("Quiz 1", 10, None))

    def fail(path, text):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(tools, "_replace_file", fail)
    assert "couldn't save your deadlines" in tools.set_mark("Quiz 1", 50)["message"]


# ---------- grade_needed: the maths ----------


def test_exact_numbers(deadlines_file):
    # Quiz 20% at 70 earns 14. 80% is left.
    save(deadlines_file, ("Quiz", 20, 70), ("Project", 30, None), ("Exam", 50, None))

    result = tools.grade_needed("41039")

    assert result["status"] == "success"
    assert (result["earned_percent"], result["still_to_come_percent"]) == (14, 80)
    assert result["marked_weight_percent"] == 20
    assert result["listed_weight_percent"] == 100
    assert bands(result) == {
        "pass": ("needed", 45.0),  # (50 - 14) / 80 = 45%
        "credit": ("needed", 63.8),  # (65 - 14) / 80 = 63.75%, rounded up
        "distinction": ("needed", 76.3),  # 76.25%
        "high distinction": ("needed", 88.8),  # 88.75%
    }
    assert result["warnings"] == []
    assert result["target"] == "credit"
    assert result["message"] == (
        "41039 Programming Fundamentals: you have earned 14% of the final mark so far, and 80% is still to come. "
        "To get a Credit (65), you need an average of 63.8% on what is left. "
        "Some subjects also have minimum rules, like a minimum exam mark, so check the subject outline."
    )


def test_already_secured(deadlines_file):
    # 60 x 90% = 54 earned, so a Pass is safe even with 0 on the exam
    save(deadlines_file, ("Assignments", 60, 90), ("Exam", 40, None))

    result = tools.grade_needed("41039", "pass")

    assert bands(result)["pass"] == ("secured", None)
    assert bands(result)["credit"] == ("needed", 27.5)  # (65 - 54) / 40
    assert "already secured a Pass (50), even with 0 on everything left" in result["message"]


def test_secured_exactly_on_the_line(deadlines_file):
    save(deadlines_file, ("Assignments", 50, 100), ("Exam", 50, None))
    assert bands(tools.grade_needed("41039"))["pass"] == ("secured", None)


def test_no_longer_reachable(deadlines_file):
    # 70% marked at 40 earns 28. Even 100% on the last 30 only gives 58.
    save(deadlines_file, ("Assignments", 70, 40), ("Exam", 30, None))

    result = tools.grade_needed("41039", "distinction")

    assert bands(result)["pass"] == ("needed", 73.4)  # (50 - 28) / 30 = 73.33%, rounded up
    assert bands(result)["credit"] == ("not_reachable", 123.4)
    assert bands(result)["distinction"] == ("not_reachable", 156.7)
    assert "A Distinction (75) is no longer reachable, because you would need an average of 156.7%" in result["message"]


def test_needing_exactly_100_is_still_reachable(deadlines_file):
    save(deadlines_file, ("Assignments", 50, 70), ("Exam", 50, None))  # 35 earned, 50 more possible
    assert bands(tools.grade_needed("41039"))["high distinction"] == ("needed", 100.0)


def test_everything_marked(deadlines_file):
    save(deadlines_file, ("Assignments", 60, 80), ("Exam", 40, 50))  # 48 + 20 = 68

    result = tools.grade_needed("41039")

    assert (result["earned_percent"], result["still_to_come_percent"]) == (68, 0)
    assert bands(result) == {
        "pass": ("secured", None),
        "credit": ("secured", None),
        "distinction": ("not_reachable", None),
        "high distinction": ("not_reachable", None),
    }
    assert "no longer reachable, because nothing is left to mark" in tools.grade_needed("41039", "hd")["message"]


def test_marks_of_0_and_100(deadlines_file):
    save(deadlines_file, ("Quiz", 50, 0), ("Project", 25, 100), ("Exam", 25, None))  # 0 + 25 earned

    result = tools.grade_needed("41039")

    assert result["earned_percent"] == 25
    assert bands(result)["pass"] == ("needed", 100.0)  # (50 - 25) / 25
    assert bands(result)["credit"] == ("not_reachable", 160.0)


def test_nothing_marked_yet(deadlines_file):
    save(deadlines_file, ("Project", 40, None), ("Exam", 60, None))

    result = tools.grade_needed("41039")

    assert (result["earned_percent"], result["still_to_come_percent"]) == (0, 100)
    assert bands(result)["credit"] == ("needed", 65.0)


def test_thirds_that_do_not_add_up_exactly_do_not_warn(deadlines_file):
    save(deadlines_file, ("A", 33.33, 60), ("B", 33.33, None), ("C", 33.34, None))
    assert tools.grade_needed("41039")["warnings"] == []


# ---------- grade_needed: missing weights and weights not adding to 100 ----------


def test_missing_weights_show_what_is_known_and_warn(deadlines_file):
    save(deadlines_file, ("Quiz", 20, 70), ("Project", None, None), ("Exam", 50, None))

    result = tools.grade_needed("41039")

    # Known: 14 earned. 80 of the 100 is not marked yet, including the 30 no deadline has
    assert (result["earned_percent"], result["still_to_come_percent"], result["listed_weight_percent"]) == (14, 80, 70)
    assert result["warnings"] == [
        "1 item (Project) has no weight, so they are left out of the maths. Add their weights from the subject outline.",
        "The weights add up to 70%, not 100%, so the numbers below assume the missing part is still to come."
        " Check the weights against the subject outline.",
    ]
    assert "Warning: 1 item (Project) has no weight" in result["message"]
    assert "Warning: The weights add up to 70%" in result["message"]


def test_a_mark_with_no_weight_is_left_out_and_warned_about(deadlines_file):
    save(deadlines_file, ("Quiz", None, 90), ("Exam", 100, None))

    result = tools.grade_needed("41039")

    assert result["earned_percent"] == 0
    assert "1 item (Quiz) has no weight" in result["warnings"][0]


def test_no_weights_at_all(deadlines_file):
    save(deadlines_file, ("Quiz", None, None), ("Exam", None, None))

    result = tools.grade_needed("41039")

    assert result["still_to_come_percent"] == 100
    assert result["warnings"][0].startswith("2 items (Quiz, Exam) have no weight")
    assert "The weights add up to 0%" in result["warnings"][1]


def test_weights_over_100_warn(deadlines_file):
    save(deadlines_file, ("Quiz", 60, 50), ("Exam", 60, None))

    result = tools.grade_needed("41039")

    assert result["warnings"] == [
        "The weights add up to 120%, which is more than 100%, so some are probably wrong and the numbers below"
        " are not reliable. Check the subject outline."
    ]
    assert result["still_to_come_percent"] == 40  # 100 - the 60 already marked


# ---------- grade_needed: finding the subject and the target ----------


@pytest.mark.parametrize("asked", ["41039", "programming fundamentals", "PROGRAMMING FUNDAMENTALS", "41039 programming  fundamentals"])
def test_subject_by_code_or_name_ignoring_case(deadlines_file, asked):
    save(deadlines_file, ("Exam", 100, None))
    assert tools.grade_needed(asked)["subject"] == SUBJECT


def test_subject_without_a_code(deadlines_file):
    tools.add_deadline("Essay", "20 nov", "Writing", 100)
    assert tools.grade_needed("writing")["status"] == "success"


def test_part_of_a_name_is_not_enough(deadlines_file):
    save(deadlines_file, ("Exam", 100, None))
    assert tools.grade_needed("Programming")["status"] == "error"


def test_unknown_subject_lists_the_known_ones(deadlines_file):
    save(deadlines_file, ("Exam", 100, None))

    result = tools.grade_needed("Maths")

    assert result == {
        "status": "error",
        "message": f"I couldn't find a subject called 'Maths'. Your subjects are: {SUBJECT}.",
    }


def test_unknown_subject_with_no_subjects_saved():
    assert "No deadline has a subject yet." in tools.grade_needed("Maths")["message"]


def test_a_name_shared_by_two_subjects_asks_which(deadlines_file):
    tools.add_deadline("A", "20 nov", "41039 Statistics")
    tools.add_deadline("B", "20 nov", "37005 Statistics")

    result = tools.grade_needed("statistics")

    assert result["status"] == "error"
    assert "matches more than one subject: 41039 Statistics, 37005 Statistics" in result["message"]


def test_empty_subject():
    assert "Tell me which subject" in tools.grade_needed("  ")["message"]


@pytest.mark.parametrize("target, key", [
    ("pass", "pass"), ("Credit", "credit"), ("DISTINCTION", "distinction"),
    ("high distinction", "high distinction"), ("HD", "high distinction"), ("p", "pass"), ("", "credit"),
])
def test_targets(deadlines_file, target, key):
    save(deadlines_file, ("Exam", 100, None))
    assert tools.grade_needed("41039", target)["target"] == key


def test_unknown_target(deadlines_file):
    save(deadlines_file, ("Exam", 100, None))

    result = tools.grade_needed("41039", "A+")

    assert result == {
        "status": "error",
        "message": "I don't know the grade 'a+'. Use pass, credit, distinction or high distinction.",
    }


def test_grade_needed_changes_nothing(deadlines_file):
    save(deadlines_file, ("Exam", 100, None))
    before = deadlines_file.read_bytes()
    tools.grade_needed("41039")
    assert deadlines_file.read_bytes() == before


def test_all_grade_reports_has_one_per_subject(deadlines_file):
    tools.add_deadline("A", "20 nov", "Writing", 50)
    tools.add_deadline("B", "21 nov", "Maths", 100)
    tools.add_deadline("C", "22 nov", "writing", 50)  # the same subject, typed differently
    tools.add_deadline("D", "23 nov")  # no subject, so no report

    reports = tools._all_grade_reports()

    assert [r["subject"] for r in reports] == ["Writing", "Maths"]
    assert [item["title"] for item in reports[0]["items"]] == ["A", "C"]


# ---------- the outline drop box passes weights through ----------


def row(title, weight, due="2026-11-20 17:00"):
    return {"title": title, "due_date": due, "subject": SUBJECT, "weight_percent": weight}


def test_save_rows_passes_each_weight(deadlines_file):
    results = importer.save_rows([row("41039 Exam", 40), row("41039 Report", 30.5), row("41039 Lab", None)])

    assert [r["status"] for r in results] == ["success"] * 3
    saved = {d["title"]: d.get("weight_percent") for d in json.loads(deadlines_file.read_text())}
    assert saved == {"41039 Exam": 40, "41039 Report": 30.5, "41039 Lab": None}
    assert "weight_percent" not in json.loads(deadlines_file.read_text())[2]  # no weight, no field


def test_save_rows_without_a_weight_key_still_works(deadlines_file):
    old_row = {"title": "41039 Exam", "due_date": "2026-11-20 17:00", "subject": SUBJECT}
    assert importer.save_rows([old_row])[0]["status"] == "success"


def test_save_rows_shares_a_weekly_series_weight_between_its_weeks(deadlines_file):
    # A 10% weekly quiz shows 10% on every week's row, but the weeks together are worth 10%
    rows = [row(f"41039 Quiz (week {week})", 10, f"2026-11-{week + 10} 17:00") for week in (1, 2, 3, 4)]
    rows.append(row("41039 Exam", 90))

    importer.save_rows(rows)

    saved = {d["title"]: d["weight_percent"] for d in json.loads(deadlines_file.read_text())}
    assert saved == {
        "41039 Quiz (week 1)": 2.5, "41039 Quiz (week 2)": 2.5, "41039 Quiz (week 3)": 2.5,
        "41039 Quiz (week 4)": 2.5, "41039 Exam": 90,
    }
    assert tools.grade_needed("41039")["warnings"] == []  # adds up to 100


def test_a_bad_weight_from_the_page_refuses_only_that_row(deadlines_file):
    results = importer.save_rows([row("41039 Exam", 140), row("41039 Report", 30)])
    assert [r["status"] for r in results] == ["error", "success"]
