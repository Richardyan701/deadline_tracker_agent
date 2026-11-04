"""Tests for the UTS timetable reader.

The fixture text follows the layout pypdf gets from a UTS timetable export,
but the rooms, class numbers and student number are all made up.
"""

import pytest

from deadline_agent import timetable

# 27/7 is a Monday, 28/7 a Tuesday and so on, in Spring 2026
FIXTURE = """\
My Timetable
Student 99887766
Spring 2026
Mon
Tue
Wed
Thu
Fri
8:00
9:00
10:00
11:00
12:00
13:00
14:00
15:00
16:00
17:00
14:00 - 15:30
48023_SPR_U_1_S
Programming Fundamentals
Olr1
07
WEB999
27/7-14/9, 28/9-19/10
9:00 - 11:00
33130_SPR_U_1_S
Mathematics 1
Tut1
03
AB01.02.300
4/8-15/9, 29/9-20/10
13:00 - 15:00
33130_SPR_U_1_S
Mathematics
1
Lec1
02
AB02.01.110
30/7-17/9, 1/10-22/10
10:00 - 12:00
35010_SPR_U_1_S
Foundation Mathematics
Wrk1
05
CD03.04.050
29/7-16/9, 30/9-21/10
16:00 - 18:00
31250_SPR_U_1_S
Introduction to Data
Analytics
Cmp1
11
EF04.05.200
31/7-18/9,
2/10-23/10
All Weeks
"""

EXPECTED = {
    "48023": [{"activity": "Olr1", "weekday": "monday", "start": "14:00", "end": "15:30"}],
    "33130": [
        {"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"},
        {"activity": "Lec1", "weekday": "thursday", "start": "13:00", "end": "15:00"},
    ],
    "35010": [{"activity": "Wrk1", "weekday": "wednesday", "start": "10:00", "end": "12:00"}],
    "31250": [{"activity": "Cmp1", "weekday": "friday", "start": "16:00", "end": "18:00"}],
}


def block(time="9:00 - 11:00", code="33130_SPR_U_1_S", name=("Mathematics 1",), activity="Tut1", dates=("4/8-15/9",)):
    """The lines of one class block, so a test can change just one field."""
    return "\n".join([time, code, *name, activity, "03", "AB01.02.300", *dates])


def make_pdf(lines: list[str]) -> bytes:
    """A small one page PDF that shows each line of text on its own line.

    PDF files are text instructions plus a table (the "xref") that says
    where each numbered object starts, so this builds the objects and then
    the table from their positions.
    """
    content = "BT /F1 10 Tf 40 800 Td 12 TL\n" + "".join(f"({line}) Tj T*\n" for line in lines) + "ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]
    pdf = "%PDF-1.4\n"
    positions = []
    for number, body in enumerate(objects, start=1):
        positions.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    table_at = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{position:010d} 00000 n \n" for position in positions)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{table_at}\n%%EOF\n"
    return pdf.encode("latin-1")


# ---------- reading the text ----------


def test_reads_every_class_grouped_by_subject():
    assert timetable.parse_timetable(FIXTURE, "SPR2026") == EXPECTED


def test_weekday_comes_from_the_first_date():
    # 5/8/2026 is a Wednesday, even though the class later runs on other dates
    found = timetable.parse_timetable(block(dates=("5/8-16/9, 30/9-21/10",)), "SPR2026")
    assert found["33130"][0]["weekday"] == "wednesday"


def test_autumn_uses_the_autumn_year():
    # 17/2/2026 is a Tuesday
    found = timetable.parse_timetable(block(code="33130_AUT_U_1_S", dates=("17/2-31/3",)), "AUT2026")
    assert found == {"33130": [{"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"}]}


def test_subject_name_wrapped_over_two_lines():
    found = timetable.parse_timetable(block(name=("Introduction to Data", "Analytics")), "SPR2026")
    assert found["33130"][0]["activity"] == "Tut1"


def test_subject_name_ending_in_a_number_wrapped_onto_its_own_line():
    # The "1" line must not be taken as the class number or the activity
    found = timetable.parse_timetable(block(name=("Mathematics", "1")), "SPR2026")
    assert found["33130"][0] == {"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"}


def test_dates_wrapped_over_two_lines():
    found = timetable.parse_timetable(block(dates=("4/8-15/9,", "29/9-20/10")), "SPR2026")
    assert found["33130"][0]["weekday"] == "tuesday"


def test_a_single_date_with_no_range():
    found = timetable.parse_timetable(block(dates=("6/8",)), "SPR2026")
    assert found["33130"][0]["weekday"] == "thursday"


@pytest.mark.parametrize(
    "time, start, end",
    [
        ("9:00 - 11:00", "09:00", "11:00"),
        ("8:30 - 9:30", "08:30", "09:30"),
        ("18:00 - 21:00", "18:00", "21:00"),
        ("10:00 – 12:00", "10:00", "12:00"),  # an en dash instead of a hyphen
        ("10:00-12:00", "10:00", "12:00"),
    ],
)
def test_times_are_24_hour_with_two_digit_hours(time, start, end):
    found = timetable.parse_timetable(block(time=time), "SPR2026")
    assert (found["33130"][0]["start"], found["33130"][0]["end"]) == (start, end)


def test_hour_labels_and_header_are_not_classes():
    header_only = "Mon\nTue\nWed\nThu\nFri\n8:00\n9:00\n10:00\nAll Weeks\n"
    with pytest.raises(ValueError, match="No classes were found"):
        timetable.parse_timetable(header_only, "SPR2026")


def test_text_after_all_weeks_is_ignored():
    text = block() + "\nAll Weeks\nPrinted 4/11/2026\nPage 1 of 1\n"
    assert timetable.parse_timetable(text, "SPR2026") == {
        "33130": [{"activity": "Tut1", "weekday": "tuesday", "start": "09:00", "end": "11:00"}]
    }


def test_two_pages_each_with_a_header():
    page_two = "Mon\nTue\nWed\nThu\nFri\n8:00\n9:00\n" + block(code="35010_SPR_U_1_S", activity="Wrk1") + "\nAll Weeks\n"
    found = timetable.parse_timetable(block() + "\nAll Weeks\n" + page_two, "SPR2026")
    assert list(found) == ["33130", "35010"]
    assert found["35010"][0]["activity"] == "Wrk1"


def test_blank_lines_and_spaces_are_ignored():
    text = "\n\n  9:00 - 11:00  \n\n33130_SPR_U_1_S\n Mathematics 1 \nTut1\n03\n\nAB01.02.300\n4/8-15/9\n"
    assert timetable.parse_timetable(text, "SPR2026")["33130"][0]["start"] == "09:00"


# ---------- clear errors ----------


@pytest.mark.parametrize("text", ["", "hello", "Mon\nTue\n9:00\n"])
def test_text_with_no_classes_is_a_clear_error(text):
    with pytest.raises(ValueError, match="No classes were found"):
        timetable.parse_timetable(text, "SPR2026")


def test_block_with_no_subject_code_is_a_clear_error():
    with pytest.raises(ValueError, match="subject code"):
        timetable.parse_timetable(block(code="Somewhere"), "SPR2026")


def test_block_with_no_activity_is_a_clear_error():
    with pytest.raises(ValueError, match="activity"):
        timetable.parse_timetable(block(activity="Tutorial"), "SPR2026")


def test_block_with_no_dates_is_a_clear_error():
    with pytest.raises(ValueError, match="dates"):
        timetable.parse_timetable(block(dates=()), "SPR2026")


def test_impossible_first_date_is_a_clear_error():
    with pytest.raises(ValueError, match="not a real date"):
        timetable.parse_timetable(block(dates=("31/2-15/9",)), "SPR2026")


def test_unknown_session_is_a_clear_error():
    with pytest.raises(ValueError, match="Unknown session"):
        timetable.parse_timetable(FIXTURE, "SPR2027")


# ---------- reading the PDF ----------


def test_reads_a_real_pdf():
    pdf = make_pdf(FIXTURE.splitlines())
    assert timetable.read_timetable(pdf, "SPR2026") == EXPECTED


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4\nbroken"])
def test_a_file_that_is_not_a_pdf_is_a_clear_error(data):
    with pytest.raises(ValueError, match="could not be read as a PDF"):
        timetable.read_timetable(data, "SPR2026")


@pytest.mark.parametrize(
    "old, new",
    [
        # One changed byte each. pypdf 6.21.4 then fails with AttributeError and TypeError,
        # not its own PyPdfError. Found by changing bytes of a good timetable at random.
        (b"trailer\n", b"trailer0"),
        (b"/Length ", b"/Length<"),
    ],
)
def test_a_damaged_pdf_that_trips_up_the_pdf_library_is_a_clear_error(old, new):
    damaged = make_pdf(FIXTURE.splitlines()).replace(old, new, 1)
    with pytest.raises(ValueError, match="could not be read as a PDF") as caught:
        timetable.read_timetable(damaged, "SPR2026")
    assert caught.value.__cause__ is not None  # the library's own error stays attached for debugging
