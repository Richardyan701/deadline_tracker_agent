"""Turn an upload from the outline drop box into rows for the review table.

The steps run in this order because Gemini's free tier only allows 20
requests a day:

1. The session and the timetable need no AI, so they are checked first, and
   a mistake there never wastes a Gemini request.
2. Each outline is sent to Gemini once. One outline failing never stops the
   others, and its problem comes back as one sentence, never a stack trace.
3. The Canvas feed is read. If it cannot be used, the preview goes on without it.
4. importer.build_preview turns everything into rows. Nothing is saved here.
"""

import importlib
import logging
from collections.abc import Callable

from deadline_agent import canvas, importer, timetable, tools, uts_calendar
from deadline_agent.import_types import CanvasEvent, ExtractedItem, PreviewRow, TimetableClass

from . import Refused
from .uploads import Pdf, Upload

logger = logging.getLogger(__name__)

# Reads one outline PDF and returns what it found. The real one is
# read_with_gemini below. The tests use a fake, so they never call Gemini.
OutlineReader = Callable[[bytes], list[ExtractedItem]]

READER_MISSING = (
    "The outline reader is not installed yet, so Groot cannot read outlines. "
    "Nothing was sent to Gemini, and the rest of Groot still works."
)
UNEXPECTED_PROBLEM = (
    "Groot could not read this outline because of an unexpected problem. "
    "The details are in the window where Groot is running."
)


class OutlineFailed(Exception):
    """Gemini could not read one outline. The message is one clear sentence for the student."""


def read_with_gemini(pdf: bytes) -> list[ExtractedItem]:
    """Read one outline with deadline_agent/outline.py, which sends it to Gemini.

    outline.py is imported here, when the first outline is read, instead of
    when Groot starts, so the rest of Groot works even while it is missing.
    Raises Refused if outline.py is not there yet, and OutlineFailed with
    outline.py's own sentence when Gemini could not read the outline.
    """
    try:
        outline = importlib.import_module("deadline_agent.outline")
    except ModuleNotFoundError as error:
        if error.name != "deadline_agent.outline":
            raise  # outline.py is there, but something it imports is missing
        raise Refused(503, READER_MISSING) from None
    try:
        return outline.extract_items(pdf)
    except outline.OutlineError as error:
        raise OutlineFailed(str(error)) from error


def build(upload: Upload, read: OutlineReader) -> dict:
    """The preview for an upload, ready to send to the page as JSON.

    Returns "outlines" (what happened to each outline file), "notes" (about
    the timetable and Canvas), "rows" (the review table, each row with an
    extra "due_text" like "Friday 14 Aug 2026, 11:59 PM") and a "message".
    Raises Refused, before any Gemini request, if the session or the
    timetable cannot be used, or if the outline reader is not installed yet.
    """
    try:
        uts_calendar.session_info(upload.session)
    except ValueError:
        raise Refused(400, "Choose the session your outlines are for: Autumn 2026 or Spring 2026.") from None
    classes = _read_timetable(upload)
    notes = [] if classes is None else ["Your timetable was read, so tutorial days come from it."]

    items, outlines = [], []
    for pdf in upload.outlines:
        found, result = _read_outline(pdf, read)
        items += found
        outlines.append(result)

    events, canvas_notes = _canvas_events(upload.canvas_url)
    rows = importer.build_preview(items, upload.session, timetable=classes, canvas_events=events)
    return {
        "status": "success",
        "message": _summary(outlines, rows),
        "outlines": outlines,
        "notes": notes + canvas_notes,
        "rows": [_with_due_text(row) for row in rows],
    }


def _read_timetable(upload: Upload) -> dict[str, list[TimetableClass]] | None:
    """The classes in the timetable PDF, or None if no timetable was added."""
    if upload.timetable is None:
        return None
    try:
        return timetable.read_timetable(upload.timetable.data, upload.session)
    except ValueError as error:  # its messages are written for the student
        raise Refused(
            400,
            f"Your timetable could not be used. {error} Remove it or choose the right file, "
            "then try again. Nothing was sent to Gemini.",
        ) from None


def _read_outline(pdf: Pdf, read: OutlineReader) -> tuple[list[ExtractedItem], dict]:
    """The items found in one outline, and a short result for the page.

    A problem with this outline becomes one sentence in the result, so the
    other outlines are still read and nothing found so far is lost.
    """
    try:
        found = read(pdf.data)
    except OutlineFailed as error:
        return [], {"file": pdf.name, "status": "error", "message": str(error)}
    except Refused:
        raise  # a problem with the whole preview, like the outline reader missing
    except Exception:
        # A bug, or a surprise from Gemini's library. The stack trace goes to
        # the window where Groot runs, never to the page.
        logger.exception("Reading the outline %s failed", pdf.name)
        return [], {"file": pdf.name, "status": "error", "message": UNEXPECTED_PROBLEM}
    if not found:
        return [], {"file": pdf.name, "status": "success", "message": "No assessments were found in this outline."}
    message = f"Found {tools._plural(len(found), 'assessment item')}."
    return found, {"file": pdf.name, "status": "success", "message": message}


def _canvas_events(link: str) -> tuple[list[CanvasEvent], list[str]]:
    """The events in the student's Canvas feed, and a note saying how it went.

    The link works like a password, so it is never logged or put in a note.
    canvas.py's messages never contain it either.
    """
    if not link:
        return [], []
    try:
        events = canvas.parse_feed(canvas.fetch_feed(link))
    except canvas.CanvasError as error:
        return [], [f"Your Canvas calendar was not used, so the preview went on without it. {error}"]
    return events, [f"Your Canvas calendar was read ({tools._plural(len(events), 'event')})."]


def _summary(outlines: list[dict], rows: list[PreviewRow]) -> str:
    """A short message about the whole preview."""
    read = sum(result["status"] == "success" for result in outlines)
    start = f"Outlines read: {read} of {len(outlines)}."
    if not rows:
        return start + " Nothing was found to save."
    return start + f" Check the {tools._plural(len(rows), 'row')} below, then save the ones you want."


def _with_due_text(row: PreviewRow) -> dict:
    """The row plus "due_text", its date in words, so the page shows dates the same way as the chat."""
    due_text = tools._friendly(tools._parse_due_date(row["due_date"])) if row["due_date"] else ""
    return {**row, "due_text": due_text}
