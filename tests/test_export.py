"""Tests for export_calendar, which saves the unfinished deadlines to an iCalendar (.ics) file.

No API key and no internet needed. Each test uses its own temporary folder
and a frozen clock. The last tests read the file back with a small strict
parser written below, so no extra package is needed.
"""

import hashlib
import json
import os
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from deadline_agent import tools

# Pretend "now" is Thursday 5 Nov 2026, 10:00 AM in Sydney, which is 11 PM on 4 Nov in UTC
NOW = datetime(2026, 11, 5, 10, 0)
STAMP = "20261104T230000Z"

NOTHING_TO_EXPORT = {
    "status": "success",
    "message": "You have no unfinished deadlines, so there is nothing to put in a calendar yet.",
    "exported": 0,
}


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Point the tools at a fresh temporary folder and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.delenv("DEADLINES_ICS_FILE", raising=False)
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


@pytest.fixture
def ics_file(deadlines_file):
    """Where export_calendar saves unless DEADLINES_ICS_FILE is set: next to deadlines.json."""
    return deadlines_file.with_name("deadlines.ics")


def save(path, *deadlines):
    """Write deadlines straight to the file, given as (title, due_date) or (title, due_date, subject, done).

    This skips add_deadline on purpose, because add_deadline refuses dates that
    have already passed and tidies line breaks out of titles.
    """
    rows = []
    for title, due_date, *rest in deadlines:
        subject, done = rest if rest else ("", False)
        rows.append({"title": title, "due_date": due_date, "subject": subject, "done": done})
    path.write_text(json.dumps(rows), encoding="utf-8")


def export_text(ics_file) -> str:
    """Run export_calendar and return the file it wrote, as text."""
    result = tools.export_calendar()
    assert result["status"] == "success", result["message"]
    return ics_file.read_bytes().decode("utf-8")


def values(text: str, name: str) -> list:
    """Every value of the property called name (like "SUMMARY"), with folded lines joined back up."""
    lines = text.replace("\r\n ", "").split("\r\n")  # a line break and a space means "same line"
    return [line.split(":", 1)[1] for line in lines if line.startswith(name + ":")]


# ---------- the exact file ----------


def test_the_file_text_is_exactly_right(deadlines_file, ics_file):
    save(
        deadlines_file,
        ("Essay", "2026-11-20", "", False),  # no time, so due at 11:59 PM, and no subject
        ("Quiz 2", "2026-11-13 17:00", "Machine Learning", False),
        ("Lab 1", "2026-11-10", "Physics", True),  # finished, so left out
    )

    result = tools.export_calendar()

    assert result == {
        "status": "success",
        "message": f"I saved 2 unfinished deadlines to this calendar file: {ics_file}",
        "exported": 2,
    }
    expected = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agent Groot//Deadline Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # Soonest first. 5:00 PM on 13 Nov in Sydney (UTC+11 in summer) is 6:00 AM in UTC.
        "BEGIN:VEVENT",
        "UID:60708b7e248d0e0f74eafa586c7dd2625c821447282c08e570663984b6668280",  # SHA-256 of "quiz 2"
        "DTSTAMP:20261104T230000Z",
        "DTSTART:20261113T060000Z",
        "DTEND:20261113T060100Z",
        "SUMMARY:Quiz 2",
        "DESCRIPTION:Subject: Machine Learning",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "TRIGGER:-P1D",
        "DESCRIPTION:Quiz 2 is due tomorrow",
        "END:VALARM",
        "END:VEVENT",
        # 11:59 PM on 20 Nov in Sydney is 12:59 PM in UTC
        "BEGIN:VEVENT",
        "UID:4231a97ecfd74fdbdde4d4306d6624330dadf659b3cd1e9b5ae35b0be2f46206",  # SHA-256 of "essay"
        "DTSTAMP:20261104T230000Z",
        "DTSTART:20261120T125900Z",
        "DTEND:20261120T130000Z",
        "SUMMARY:Essay",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "TRIGGER:-P1D",
        "DESCRIPTION:Essay is due tomorrow",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    # Every line, including the last one, ends with CRLF (\r\n)
    assert ics_file.read_bytes() == ("\r\n".join(expected) + "\r\n").encode("utf-8")


def test_one_deadline_says_deadline_not_deadlines(deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20"))

    result = tools.export_calendar()

    assert result["message"] == f"I saved 1 unfinished deadline to this calendar file: {ics_file}"
    assert result["exported"] == 1


# ---------- escaping ----------


@pytest.mark.parametrize(
    "title, summary",
    [
        ("Essay, part 1", "Essay\\, part 1"),
        ("Essay; part 1", "Essay\\; part 1"),
        ("C:\\Uni\\essay", "C:\\\\Uni\\\\essay"),  # each backslash becomes two
        ("Ends with \\", "Ends with \\\\"),
        ("\\,\\;", "\\\\\\,\\\\\\;"),  # a backslash before a comma or semicolon is not mixed up with an escape
        ("Week 3: quiz", "Week 3: quiz"),  # a colon is never escaped
        ('Bob\'s "big" essay', 'Bob\'s "big" essay'),  # quotes are fine as they are
        # Line breaks can only come from a hand-edited deadlines file
        ("Line one\nLine two", "Line one\\nLine two"),
        ("Line one\r\nLine two", "Line one\\nLine two"),  # a Windows line break is one line break too
        # Other control characters are not allowed in the file, so they become spaces
        ("Bell\x07 and tab\t", "Bell  and tab "),
        # Half of a broken character (only from a hand-edited file) cannot be saved, and must not crash
        ("Broken \ud800 char", "Broken   char"),
        ("Café 论文 😀", "Café 论文 😀"),  # other languages and emoji are kept
    ],
)
def test_titles_are_escaped(title, summary, deadlines_file, ics_file):
    save(deadlines_file, (title, "2026-11-20"))

    text = export_text(ics_file)

    assert values(text, "SUMMARY") == [summary]
    assert values(text, "DESCRIPTION") == [summary + " is due tomorrow"]  # the reminder


def test_subjects_are_escaped(deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20", "Maths, Stats; Data \\ Science", False))

    text = export_text(ics_file)

    assert values(text, "DESCRIPTION")[0] == "Subject: Maths\\, Stats\\; Data \\\\ Science"


# ---------- folding long lines ----------


def test_a_long_title_is_folded_at_75_bytes(deadlines_file, ics_file):
    save(deadlines_file, ("T" * 200, "2026-11-20"))

    lines = export_text(ics_file).split("\r\n")

    # "SUMMARY:" is 8 bytes, so the first line has room for 67 T's.
    # Each extra line starts with a space and has room for 74 more.
    start = lines.index("SUMMARY:" + "T" * 67)
    assert lines[start : start + 3] == ["SUMMARY:" + "T" * 67, " " + "T" * 74, " " + "T" * 59]
    assert max(len(line.encode("utf-8")) for line in lines) == 75


def test_folding_never_cuts_a_character_in_half(deadlines_file, ics_file):
    # In UTF-8 each Chinese character here is 3 bytes and the emoji is 4 bytes
    title = "论文" * 40 + "😀" * 20
    save(deadlines_file, (title, "2026-11-20"))

    text = export_text(ics_file)

    # 8 bytes for "SUMMARY:" and 22 characters of 3 bytes is 74 bytes. One more would make 77.
    assert "\r\nSUMMARY:" + "论文" * 11 + "\r\n " in text
    for line in ics_file.read_bytes().split(b"\r\n"):
        assert len(line) <= 75
        line.decode("utf-8")  # fails if a character was cut in half
    assert values(text, "SUMMARY") == [title]


# ---------- times in UTC ----------


@pytest.mark.parametrize(
    "due_date, start",
    [
        # Sunday 5 Apr 2026: at 3 AM daylight saving ends and the clocks go back to 2 AM (UTC+11 becomes UTC+10)
        ("2026-04-04", "20260404T125900Z"),  # 11:59 PM the night before, still UTC+11
        ("2026-04-05 01:30", "20260404T143000Z"),  # before the change, UTC+11
        ("2026-04-05 02:30", "20260404T153000Z"),  # happens twice that night, and the first one (UTC+11) is used
        ("2026-04-05 03:30", "20260404T173000Z"),  # after the change, UTC+10
        ("2026-04-05", "20260405T135900Z"),  # 11:59 PM, UTC+10
        # Sunday 4 Oct 2026: at 2 AM daylight saving starts and the clocks jump to 3 AM (UTC+10 becomes UTC+11)
        ("2026-10-03", "20261003T135900Z"),  # 11:59 PM the night before, still UTC+10
        ("2026-10-04 01:30", "20261003T153000Z"),  # before the change, UTC+10
        ("2026-10-04 02:30", "20261003T163000Z"),  # does not exist that night, so it counts as 3:30 AM
        ("2026-10-04 03:30", "20261003T163000Z"),  # after the change, UTC+11
        ("2026-10-04", "20261004T125900Z"),  # 11:59 PM, UTC+11
    ],
)
def test_times_are_utc_on_the_daylight_saving_change_days(due_date, start, deadlines_file, ics_file):
    save(deadlines_file, ("Task", due_date))

    text = export_text(ics_file)

    assert values(text, "DTSTART") == [start]
    end = values(text, "DTEND")[0]
    length = datetime.strptime(end, "%Y%m%dT%H%M%SZ") - datetime.strptime(start, "%Y%m%dT%H%M%SZ")
    assert length == timedelta(minutes=1)


# ---------- stable UIDs ----------


def test_uid_stays_the_same_when_the_date_or_subject_changes(deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20", "Writing", False))
    first = values(export_text(ics_file), "UID")

    save(deadlines_file, ("Essay", "2026-11-27 09:00", "Academic Writing", False))
    second = values(export_text(ics_file), "UID")

    # The same UID tells a calendar app it is the same event, so it can update it instead of adding a copy
    assert first == second == [hashlib.sha256(b"essay").hexdigest()]


@pytest.mark.parametrize("same_title", ["ESSAY", "  essay ", "Ｅssay"])  # the last one starts with a full width E
def test_titles_that_look_the_same_get_the_same_uid(same_title, deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20"))
    first = values(export_text(ics_file), "UID")

    save(deadlines_file, (same_title, "2026-11-20"))

    assert values(export_text(ics_file), "UID") == first


def test_different_titles_get_different_uids(deadlines_file, ics_file):
    save(deadlines_file, ("Essay 1", "2026-11-20"), ("Essay 2", "2026-11-20"), ("Essay", "2026-11-20"))

    uids = values(export_text(ics_file), "UID")

    assert len(set(uids)) == 3


def test_uids_follow_the_icalendar_rules(deadlines_file, ics_file):
    # RFC 7986 asks for an ID under 255 bytes, made of letters, digits and hyphens,
    # that does not show anything about the user or their computer
    save(deadlines_file, ("Quiz, week 3; part 😀 \\", "2026-11-20"), ("Broken \ud800", "2026-11-21"))

    for uid in values(export_text(ics_file), "UID"):
        assert re.fullmatch(r"[0-9a-f]{64}", uid)


# ---------- what goes in the file ----------


def test_finished_deadlines_are_left_out_and_overdue_ones_are_kept(deadlines_file, ics_file):
    save(
        deadlines_file,
        ("Report", "2026-11-25", "", False),
        ("Finished essay", "2026-11-20", "", True),
        ("Late quiz", "2026-11-01", "", False),  # overdue but not finished, so still exported
    )

    result = tools.export_calendar()

    assert result["exported"] == 2
    assert values(ics_file.read_bytes().decode("utf-8"), "SUMMARY") == ["Late quiz", "Report"]  # soonest first


def test_an_empty_list_writes_no_file(deadlines_file, ics_file):
    save(deadlines_file)  # an empty list

    # A calendar file must hold at least one event, so none is made
    assert tools.export_calendar() == NOTHING_TO_EXPORT
    assert not ics_file.exists()


def test_only_finished_deadlines_writes_no_file(deadlines_file, ics_file):
    save(deadlines_file, ("Finished essay", "2026-11-20", "", True))

    assert tools.export_calendar() == NOTHING_TO_EXPORT
    assert not ics_file.exists()


def test_no_deadlines_file_at_all_writes_no_file(deadlines_file, ics_file):
    assert tools.export_calendar() == NOTHING_TO_EXPORT
    assert [p.name for p in deadlines_file.parent.iterdir()] == []


def test_an_unreadable_deadlines_file_is_left_alone(deadlines_file, ics_file):
    deadlines_file.write_text("{broken", encoding="utf-8")

    assert tools.export_calendar() == NOTHING_TO_EXPORT
    assert deadlines_file.read_text(encoding="utf-8") == "{broken"
    assert not ics_file.exists()


def test_exporting_again_replaces_the_old_file(deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20"))
    export_text(ics_file)
    save(deadlines_file, ("Quiz", "2026-11-21"))

    assert values(export_text(ics_file), "SUMMARY") == ["Quiz"]
    assert sorted(p.name for p in ics_file.parent.iterdir()) == ["deadlines.ics", "deadlines.json"]


# ---------- where the file goes ----------


def test_deadlines_ics_file_chooses_where_it_is_saved(tmp_path, monkeypatch, deadlines_file, ics_file):
    custom = tmp_path / "My Calendar" / "uni.ics"
    custom.parent.mkdir()
    monkeypatch.setenv("DEADLINES_ICS_FILE", str(custom))
    save(deadlines_file, ("Essay", "2026-11-20"))

    result = tools.export_calendar()

    assert result["message"] == f"I saved 1 unfinished deadline to this calendar file: {custom}"
    assert b"SUMMARY:Essay\r\n" in custom.read_bytes()
    assert not ics_file.exists()


def test_default_calendar_file_is_next_to_the_package(monkeypatch):
    monkeypatch.delenv("DEADLINES_FILE")

    assert tools._calendar_file() == Path(tools.__file__).parent.parent / "deadlines.ics"


# ---------- the lock and failed saves ----------


def test_the_lock_is_held_while_reading_and_writing(deadlines_file, monkeypatch):
    save(deadlines_file, ("Essay", "2026-11-20"))
    seen = []
    real_load, real_replace = tools._load_deadlines, tools._replace_file

    def load():
        seen.append(("read", tools._file_lock.locked()))
        return real_load()

    def replace(path, text):
        seen.append(("write", tools._file_lock.locked()))
        real_replace(path, text)

    monkeypatch.setattr(tools, "_load_deadlines", load)
    monkeypatch.setattr(tools, "_replace_file", replace)

    tools.export_calendar()

    assert seen == [("read", True), ("write", True)]


def test_export_waits_while_another_tool_call_has_the_lock(deadlines_file, ics_file):
    save(deadlines_file, ("Essay", "2026-11-20"))

    with tools._file_lock:  # pretend another tool call is changing the deadlines right now
        thread = threading.Thread(target=tools.export_calendar)
        thread.start()
        thread.join(timeout=0.2)
        assert thread.is_alive()  # still waiting for the lock
        assert not ics_file.exists()
    thread.join()

    assert ics_file.exists()


def test_a_failed_save_is_a_clear_error_and_keeps_the_old_file(deadlines_file, ics_file, monkeypatch):
    save(deadlines_file, ("Essay", "2026-11-20"))
    export_text(ics_file)
    before = ics_file.read_bytes()
    save(deadlines_file, ("Essay", "2026-11-20"), ("Quiz", "2026-11-21"))

    def file_in_use(source, target):
        raise PermissionError(13, "Access is denied")  # what Windows says when another program has it open

    monkeypatch.setattr(os, "replace", file_in_use)

    result = tools.export_calendar()

    assert result == {
        "status": "error",
        "message": "I couldn't save your calendar file (Access is denied). Please check its folder is not "
        "read only and the file is not open in another program, then try again.",
    }
    assert ics_file.read_bytes() == before
    assert sorted(p.name for p in ics_file.parent.iterdir()) == ["deadlines.ics", "deadlines.json"]  # no temporary file left


def test_saving_into_a_missing_folder_is_a_clear_error(tmp_path, monkeypatch, deadlines_file):
    monkeypatch.setenv("DEADLINES_ICS_FILE", str(tmp_path / "no such folder" / "deadlines.ics"))
    save(deadlines_file, ("Essay", "2026-11-20"))

    result = tools.export_calendar()

    assert result["status"] == "error"
    assert result["message"].startswith("I couldn't save your calendar file (No such file or directory)")
    assert str(tmp_path) not in result["message"]  # no folder names are sent to the model


def test_the_docstring_tells_gemini_when_to_call_it_and_how_to_import():
    doc = tools.export_calendar.__doc__

    for phrase in ["add these to my calendar", "export my deadlines", "Import & export", "iPhone", "Android"]:
        assert phrase in doc


# ---------- reading the file back with a small strict parser ----------

# A property name like "DTSTART" or "X-WR-CALNAME"
NAME = re.compile(r"[A-Z]+(-[A-Z]+)*")
# Escaped text: any character except \ ; and , unless it is one of the escapes \\ \; \, \n or \N
TEXT = re.compile(r"(?:[^\\;,]|\\[\\;,nN])*")
UTC_TIME = re.compile(r"[0-9]{8}T[0-9]{6}Z")


def parse(data: bytes) -> dict:
    """Read an .ics file strictly, and fail the test on anything that breaks RFC 5545.

    Returns the calendar as {"name": "VCALENDAR", "props": {...}, "children": [...]},
    where props maps each property name to a list of its values and children
    are the components inside it (each VEVENT, and each VALARM in those).
    """
    assert data.endswith(b"\r\n"), "the last line must end with CRLF"
    lines = []
    for raw in data[:-2].split(b"\r\n"):
        assert len(raw) <= 75, f"line longer than 75 bytes: {raw!r}"
        line = raw.decode("utf-8")  # fails on a character cut in half
        assert not any(unicodedata.category(char) == "Cc" for char in line), f"control character in {line!r}"
        if line.startswith(" "):
            assert lines, "the first line cannot be a folded line"
            lines[-1] += line[1:]  # a folded line continues the one before it
        else:
            lines.append(line)

    calendar, open_components = None, []
    for line in lines:
        name, colon, value = line.partition(":")
        assert colon and NAME.fullmatch(name), f"not a NAME:value line: {line!r}"
        if name == "BEGIN":
            component = {"name": value, "props": {}, "children": []}
            if open_components:
                open_components[-1]["children"].append(component)
            else:
                assert calendar is None, "only one calendar is allowed"
                calendar = component
            open_components.append(component)
        elif name == "END":
            assert open_components and open_components.pop()["name"] == value, f"END:{value} does not match"
        else:
            assert open_components, f"{name} is outside every component"
            open_components[-1]["props"].setdefault(name, []).append(value)
    assert not open_components, "a component was never closed"
    assert calendar["name"] == "VCALENDAR"
    return calendar


def once(component: dict, name: str) -> str:
    """The value of a property that must appear exactly once."""
    found = component["props"].get(name, [])
    assert len(found) == 1, f"{component['name']} must have exactly one {name}, but has {len(found)}"
    return found[0]


def unescape(value: str) -> str:
    """Turn escaped iCalendar text back into the original text."""
    assert TEXT.fullmatch(value), f"badly escaped text: {value!r}"
    return re.sub(r"\\(.)", lambda match: "\n" if match[1] in "nN" else match[1], value)


def test_round_trip_through_a_strict_parser(deadlines_file, ics_file):
    deadlines = [
        ("Essay, part 1; final \\ draft: v2", "2026-11-20", "Writing, Academic", False),
        ("论文 " * 30 + "😀" * 10, "2026-04-05 02:30", "", False),
        ("Café quiz", "2026-10-04 09:00", "Français", False),
        ("Finished already", "2026-11-21", "", True),
        ("Line one\nLine two", "2026-11-30", "", False),
        ("T" * 300, "2026-12-01 17:00", "Long " * 40, False),
    ]
    save(deadlines_file, *deadlines)
    tools.export_calendar()

    calendar = parse(ics_file.read_bytes())

    assert once(calendar, "VERSION") == "2.0"
    assert once(calendar, "PRODID") == "-//Agent Groot//Deadline Export//EN"
    assert once(calendar, "METHOD") == "PUBLISH"
    # Soonest first, finished one left out, with each start worked out by hand from Sydney time
    expected = [
        (deadlines[1], "20260404T153000Z"),  # 2:30 AM on 5 Apr happens twice, the first one is UTC+11
        (deadlines[2], "20261003T220000Z"),  # 9:00 AM on 4 Oct, UTC+11
        (deadlines[0], "20261120T125900Z"),  # 11:59 PM, UTC+11
        (deadlines[4], "20261130T125900Z"),
        (deadlines[5], "20261201T060000Z"),  # 5:00 PM, UTC+11
    ]
    events = calendar["children"]
    assert [event["name"] for event in events] == ["VEVENT"] * len(expected)
    assert len({once(event, "UID") for event in events}) == len(expected)

    for event, ((title, due_date, subject, done), start) in zip(events, expected):
        assert unescape(once(event, "SUMMARY")) == title
        assert once(event, "DTSTAMP") == STAMP
        assert once(event, "DTSTART") == start
        end = once(event, "DTEND")
        assert UTC_TIME.fullmatch(start) and UTC_TIME.fullmatch(end)
        assert end > start  # RFC 5545 says the end must come after the start
        if subject:
            assert unescape(once(event, "DESCRIPTION")) == "Subject: " + subject
        else:
            assert "DESCRIPTION" not in event["props"]

        [alarm] = event["children"]
        assert alarm["name"] == "VALARM"
        assert once(alarm, "ACTION") == "DISPLAY"
        assert once(alarm, "TRIGGER") == "-P1D"
        assert unescape(once(alarm, "DESCRIPTION")) == title + " is due tomorrow"


def test_the_strict_parser_catches_broken_files():
    # Make sure the parser really is strict, so the round trip test means something
    good = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    assert parse(good.encode("utf-8"))["props"] == {"VERSION": ["2.0"]}

    broken_files = [
        good.replace("\r\n", "\n"),  # LF instead of CRLF
        good[:-2],  # no CRLF at the end
        good.replace("VERSION:2.0", "VERSION:" + "2" * 80),  # a line over 75 bytes
        good.replace("END:VCALENDAR", "END:VEVENT"),  # BEGIN and END do not match
        good.replace("VERSION:2.0", "version 2.0"),  # not a NAME:value line
    ]
    for text in broken_files:
        with pytest.raises(AssertionError):
            parse(text.encode("utf-8"))
    for text in ["a,b", "a;b", "a\\b", "ends with \\"]:
        with pytest.raises(AssertionError):
            unescape(text)
