"""Tests for the Canvas calendar feed reader.

No test goes on the internet. httpx's MockTransport answers instead of
Canvas, and the feeds below are made up in Canvas's format.
"""

import logging
import traceback

import httpx
import pytest

from deadline_agent import canvas

# A made-up feed link. The part after user_ works like a password.
SECRET = "user_9f8e7d6c5b4a3"
LINK = f"https://canvas.uts.edu.au/feeds/calendars/{SECRET}.ics"


def feed(*events: str) -> bytes:
    """A calendar feed like Canvas sends, with one VEVENT for each text given."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Instructure//Canvas//EN", "X-WR-CALNAME:Test Calendar"]
    for event in events:
        lines += ["BEGIN:VEVENT", *event.strip().splitlines(), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode()


def event(summary: str, start: str = "DTSTART:20261005T125900Z", uid: str = "event-assignment-1001") -> str:
    """The lines of one Canvas event."""
    return f"DTSTAMP:20261101T000000Z\n{start}\nSUMMARY:{summary}\nUID:{uid}\nURL:https://example.edu/courses/1"


# ---------- parse_feed ----------


def test_reads_an_assignment():
    events = canvas.parse_feed(feed(event("Assignment 2 [33130_SPR_U_1_S]")))
    assert events == [{
        "subject_code": "33130",
        "title": "Assignment 2",
        "due": "2026-10-05 23:59",
        "all_day": False,
        "uid": "event-assignment-1001",
    }]


@pytest.mark.parametrize(
    "utc, sydney",
    [
        # Daylight saving starts at 2 AM on Sunday 4 Oct 2026 (UTC+10 becomes UTC+11)
        ("20261003T135900Z", "2026-10-03 23:59"),  # +10
        ("20261003T155900Z", "2026-10-04 01:59"),  # one minute before the change, still +10
        ("20261003T160000Z", "2026-10-04 03:00"),  # the change: 2 AM jumps to 3 AM
        ("20261004T125900Z", "2026-10-04 23:59"),  # +11
        ("20261005T125900Z", "2026-10-05 23:59"),  # +11
        ("20261005T135900Z", "2026-10-06 00:59"),  # the same UTC clock as the first row, an hour later in Sydney
        # Daylight saving ends at 3 AM on Sunday 5 Apr 2026 (UTC+11 becomes UTC+10)
        ("20260404T125900Z", "2026-04-04 23:59"),  # +11
        ("20260405T135900Z", "2026-04-05 23:59"),  # +10
    ],
)
def test_utc_times_become_sydney_times_across_daylight_saving(utc, sydney):
    events = canvas.parse_feed(feed(event("Quiz [33130_SPR_U_1_S]", start=f"DTSTART:{utc}")))
    assert events[0]["due"] == sydney


def test_time_with_a_sydney_timezone():
    events = canvas.parse_feed(feed(event("Quiz [33130]", start="DTSTART;TZID=Australia/Sydney:20261005T170000")))
    assert events[0]["due"] == "2026-10-05 17:00"


def test_time_with_no_timezone_counts_as_sydney():
    events = canvas.parse_feed(feed(event("Quiz [33130]", start="DTSTART:20261005T170000")))
    assert events[0]["due"] == "2026-10-05 17:00"


def test_all_day_event_is_due_by_the_end_of_the_day():
    events = canvas.parse_feed(feed(event("Field trip [33130_SPR_U_1_S]", start="DTSTART;VALUE=DATE:20261009")))
    assert events[0]["due"] == "2026-10-09 23:59"
    assert events[0]["all_day"] is True


def test_event_with_no_course_code():
    events = canvas.parse_feed(feed(event("Dentist", uid="event-calendar-event-77")))
    assert events[0]["subject_code"] == ""
    assert events[0]["title"] == "Dentist"


def test_course_code_from_the_tag_and_tag_left_out_of_the_title():
    events = canvas.parse_feed(feed(event("Skills Test 3 [33130 Mathematics 1 Spring 2026]")))
    assert (events[0]["subject_code"], events[0]["title"]) == ("33130", "Skills Test 3")


def test_course_code_in_the_title_with_no_tag():
    events = canvas.parse_feed(feed(event("31250 Project check-in")))
    assert (events[0]["subject_code"], events[0]["title"]) == ("31250", "31250 Project check-in")


def test_first_five_digit_number_wins():
    events = canvas.parse_feed(feed(event("Reading 31265 notes [33130_SPR_U_1_S]")))
    assert events[0]["subject_code"] == "31265"


def test_longer_numbers_are_not_subject_codes():
    events = canvas.parse_feed(feed(event("Booking 123456 [Room 2026]")))
    assert events[0]["subject_code"] == ""


def test_escaped_commas_in_the_title():
    events = canvas.parse_feed(feed(event("Report\\, part 1 [33130_SPR_U_1_S]")))
    assert events[0]["title"] == "Report, part 1"


def test_events_keep_the_feed_order_and_an_empty_feed_has_none():
    events = canvas.parse_feed(feed(event("B [33130]", uid="b"), event("A [33130]", uid="a")))
    assert [one["uid"] for one in events] == ["b", "a"]
    assert canvas.parse_feed(feed()) == []


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html><body>Please log in</body></html>",
        b"BEGIN:VEVENT\r\nSUMMARY:x\r\nDTSTART:20261005T125900Z\r\nEND:VEVENT\r\n",  # an event with no calendar
    ],
)
def test_data_that_is_not_a_calendar_is_a_clear_error(data):
    with pytest.raises(canvas.CanvasError, match="did not give a calendar"):
        canvas.parse_feed(data)


def test_event_with_no_start_is_a_clear_error():
    with pytest.raises(canvas.CanvasError, match="did not give a calendar"):
        canvas.parse_feed(feed("SUMMARY:Quiz [33130]\nUID:x"))


# ---------- check_link ----------


@pytest.mark.parametrize(
    "link",
    [
        LINK,
        f"https://uts.instructure.com/feeds/calendars/{SECRET}.ics",
        f"  https://CANVAS.uts.edu.au/feeds/calendars/{SECRET}.ics\n",  # spaces and capitals from pasting
    ],
)
def test_canvas_links_are_accepted(link):
    assert canvas.check_link(link).host in ("canvas.uts.edu.au", "uts.instructure.com")


@pytest.mark.parametrize(
    "link",
    [
        f"http://canvas.uts.edu.au/feeds/calendars/{SECRET}.ics",  # not https
        f"ftp://canvas.uts.edu.au/{SECRET}.ics",
        f"https://canvas.uts.edu.au.evil.example/{SECRET}.ics",
        f"https://evil.example/canvas.uts.edu.au/{SECRET}.ics",
        f"https://canvas.uts.edu.au@evil.example/{SECRET}.ics",  # really goes to evil.example
        f"https://instructure.com/{SECRET}.ics",  # only names ending in .instructure.com
        f"https://evilinstructure.com/{SECRET}.ics",
        f"https://uts.instructure.com.evil.example/{SECRET}.ics",
        f"https://127.0.0.1/{SECRET}.ics",
        f"https://localhost/{SECRET}.ics",
        f"canvas.uts.edu.au/{SECRET}.ics",  # no https:// at all
        f"https://canvas.uts.edu.au/{SECRET}\x00.ics",  # a hidden control character
        "",
    ],
)
def test_other_links_are_refused_without_repeating_the_link(link):
    with pytest.raises(canvas.CanvasError) as caught:
        canvas.check_link(link)
    assert SECRET not in str(caught.value)


# ---------- fetch_feed ----------


@pytest.fixture
def fake_canvas(monkeypatch):
    """Make httpx.Client answer with a handler function instead of the internet.

    Returns a function that takes the handler and gives back a list that
    fills up with the settings each client was made with.
    """
    real_client = httpx.Client

    def install(handler):
        settings_used = []

        def client(**settings):
            settings_used.append(settings)
            return real_client(transport=httpx.MockTransport(handler), **settings)

        monkeypatch.setattr(httpx, "Client", client)
        return settings_used

    return install


def full_error_text(error: BaseException) -> str:
    """Everything that would be printed if the error was logged with its traceback."""
    return "".join(traceback.format_exception(error))


def test_fetch_returns_the_feed(fake_canvas):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=feed(event("Quiz [33130]")))

    settings_used = fake_canvas(handler)
    data = canvas.fetch_feed(LINK)

    assert canvas.parse_feed(data)[0]["title"] == "Quiz"
    assert [(r.method, str(r.url)) for r in requests] == [("GET", LINK)]
    assert settings_used == [{"timeout": 10}]


def test_refused_link_is_never_fetched(fake_canvas):
    def handler(request):
        raise AssertionError("a refused link must not be fetched")

    fake_canvas(handler)
    with pytest.raises(canvas.CanvasError, match="https"):
        canvas.fetch_feed(f"http://canvas.uts.edu.au/feeds/calendars/{SECRET}.ics")


def test_redirects_are_not_followed(fake_canvas):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    fake_canvas(handler)
    with pytest.raises(canvas.CanvasError, match="302") as caught:
        canvas.fetch_feed(LINK)
    assert len(requests) == 1
    assert SECRET not in full_error_text(caught.value)


def test_error_status_is_a_clear_error(fake_canvas):
    fake_canvas(lambda request: httpx.Response(404, content=b"Not found"))
    with pytest.raises(canvas.CanvasError, match="404") as caught:
        canvas.fetch_feed(LINK)
    assert SECRET not in full_error_text(caught.value)


def test_a_feed_of_exactly_2_mb_is_read(fake_canvas):
    fake_canvas(lambda request: httpx.Response(200, content=b"x" * canvas.MAX_BYTES))
    assert len(canvas.fetch_feed(LINK)) == 2 * 1024 * 1024


def test_a_feed_over_2_mb_is_refused(fake_canvas):
    fake_canvas(lambda request: httpx.Response(200, content=b"x" * (canvas.MAX_BYTES + 1)))
    with pytest.raises(canvas.CanvasError, match="2 MB"):
        canvas.fetch_feed(LINK)


def test_timeout_is_a_clear_error_without_the_link(fake_canvas):
    def handler(request):
        raise httpx.ReadTimeout(f"timed out reading {request.url}", request=request)

    fake_canvas(handler)
    with pytest.raises(canvas.CanvasError, match="10 seconds") as caught:
        canvas.fetch_feed(LINK)
    assert SECRET not in full_error_text(caught.value)


def test_connection_error_is_a_clear_error_without_the_link(fake_canvas):
    def handler(request):
        raise httpx.ConnectError(f"could not connect to {request.url}", request=request)

    fake_canvas(handler)
    with pytest.raises(canvas.CanvasError, match="could not be reached") as caught:
        canvas.fetch_feed(LINK)
    assert SECRET not in full_error_text(caught.value)


def test_the_link_is_never_logged(fake_canvas, caplog):
    caplog.set_level(logging.DEBUG)
    fake_canvas(lambda request: httpx.Response(200, content=feed()))
    canvas.fetch_feed(LINK)
    # httpx still logs requests to other sites, so the check above really looked at its log
    with httpx.Client() as client:
        client.get("https://example.com/other")

    assert "example.com/other" in caplog.text
    assert SECRET not in caplog.text
