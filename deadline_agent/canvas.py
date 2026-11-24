"""Read the student's Canvas calendar feed. Plain code, no AI.

The student copies the feed link from Canvas (Calendar, Calendar Feed). The
link has a secret code in it, so anyone who has it can read the calendar.
That is why the link is never logged, stored or put in an error message.

Getting the feed (fetch_feed) and reading it (parse_feed) are separate, so
the tests can check the reading part without going on the internet.
"""

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import icalendar

from .import_types import CanvasEvent
from .tools import SUBJECT_CODE as CODE_SHAPE
from . import tools


# Only links to these hosts are fetched, so the server cannot be tricked into
# visiting some other site. UTS and USyd use Canvas. UNSW and Macquarie use
# Moodle instead, which Groot cannot read yet.
CANVAS_HOSTS = ("canvas.uts.edu.au", "canvas.sydney.edu.au")
INSTRUCTURE_DOMAIN = ".instructure.com"  # any host ending in this, like uts.instructure.com

TIMEOUT_SECONDS = 10
MAX_BYTES = 2 * 1024 * 1024  # 2 MB

# A subject code like "33130" or "COMP1511" that is not part of a longer word or number
SUBJECT_CODE = re.compile(rf"(?<![A-Za-z0-9]){CODE_SHAPE}(?![A-Za-z0-9])")
COURSE_TAG = re.compile(r"(.*?) *\[([^\]]*)\] *")  # "Assignment 2 [33130_SPR_U_1_S]"


class CanvasError(Exception):
    """A problem with the Canvas feed. The message is safe to show the student."""


class _HideCanvasLinks(logging.Filter):
    """httpx logs every request with its full link, so drop the lines about Canvas."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return INSTRUCTURE_DOMAIN not in message and not any(host in message for host in CANVAS_HOSTS)


logging.getLogger("httpx").addFilter(_HideCanvasLinks())


def check_link(link: str) -> httpx.URL:
    """The link as an httpx.URL, if it is an https link to a Canvas host.

    Raises CanvasError otherwise. The same URL object is checked here and
    then fetched, so the check and the fetch can never disagree about the host.
    """
    try:
        url = httpx.URL(link.strip())
    except (httpx.InvalidURL, ValueError):  # for example a space or a control character in it
        raise CanvasError("That is not a valid web link. Copy it again from Canvas, Calendar, Calendar Feed.") from None
    if url.scheme != "https":
        raise CanvasError("The Canvas link must start with https://.")
    if url.host not in CANVAS_HOSTS and not url.host.endswith(INSTRUCTURE_DOMAIN):
        raise CanvasError(f"Only Canvas links from {', '.join(CANVAS_HOSTS)} or instructure.com can be used.")
    return url


def fetch_feed(link: str) -> bytes:
    """Download the Canvas calendar feed once and return its bytes.

    Only https links to the hosts in CANVAS_HOSTS or *.instructure.com are fetched.
    Redirects are not followed, the wait is at most 10 seconds and the feed
    can be at most 2 MB. Raises CanvasError with a message that never
    contains the link.
    """
    url = check_link(link)
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise CanvasError(
                        f"Canvas answered with code {response.status_code} instead of the calendar. "
                        "Copy the link again from Canvas, Calendar, Calendar Feed."
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise CanvasError("The Canvas calendar is bigger than 2 MB, so it was not read.")
    # "from None" leaves out httpx's own error, which has the link in it
    except httpx.TimeoutException:
        raise CanvasError(f"Canvas did not answer within {TIMEOUT_SECONDS} seconds. Try again later.") from None
    except httpx.HTTPError:
        raise CanvasError("Canvas could not be reached. Check your internet connection and try again.") from None
    return bytes(data)


def _sydney_due(start) -> str:
    """An event's start as local time "YYYY-MM-DD HH:MM" (see tools.LOCAL_TIME)."""
    if isinstance(start, datetime):
        if start.tzinfo is not None:
            start = start.astimezone(tools.LOCAL_TIME)
        # A time with no timezone ("floating") already means local time
        return start.strftime("%Y-%m-%d %H:%M")
    # An all-day event has a date but no time, so it is due by the end of that day
    return f"{start.isoformat()} 23:59"


def parse_feed(data: bytes) -> list[CanvasEvent]:
    """The events in a Canvas calendar feed, in local time.

    Canvas titles end with the course in square brackets, like
    "Assignment 2 [33130_SPR_U_1_S]". The tag is removed from the title. The
    subject code (like "33130" or "COMP1511") is the first one in the tag, or
    else the first one in the title ("" if there is none, for example a
    personal event).
    Raises CanvasError if the data is not a calendar.
    """
    try:
        calendar = icalendar.Calendar.from_ical(data)
        if not isinstance(calendar, icalendar.Calendar):
            raise ValueError("not a VCALENDAR")
        events = []
        for event in calendar.events:
            summary = str(event.get("SUMMARY", ""))
            tagged = COURSE_TAG.fullmatch(summary)
            # The course tag is checked first, so a word in the title that only looks like a code never wins
            code = (tagged and SUBJECT_CODE.search(tagged[2])) or SUBJECT_CODE.search(summary)
            events.append({
                "subject_code": code[0] if code else "",
                "title": (tagged[1] if tagged else summary).strip(),
                "due": _sydney_due(event.start),  # raises ValueError if the event has no start
                "all_day": not isinstance(event.start, datetime),
                "uid": str(event.get("UID", "")),
            })
    except Exception as error:  # a damaged feed can make icalendar raise many kinds of error, not only ValueError
        raise CanvasError(
            "The Canvas link did not give a calendar. Copy the link again from Canvas, Calendar, Calendar Feed."
        ) from error
    return events
