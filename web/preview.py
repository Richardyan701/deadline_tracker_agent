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

from deadline_agent import calendars, canvas, importer, model_choice, privacy, timetable, tools
from deadline_agent.import_types import CanvasEvent, ExtractedItem, PreviewRow, TimetableClass

from . import Refused
from .uploads import Upload, UploadedFile

logger = logging.getLogger(__name__)

# Reads one outline file, given its bytes, its name and a list to add to, and
# returns what it found. The kinds of sensitive detail it took out before
# sending (like "card number") are added to the list. The real one is
# read_with_gemini below. The tests use a fake, so they never call Gemini.
OutlineReader = Callable[[bytes, str, list], list[ExtractedItem]]

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


def read_with_gemini(data: bytes, filename: str, removed: list | None = None) -> list[ExtractedItem]:
    """Read one outline file with deadline_agent/outline.py, which sends it to Gemini.

    filename, like "33130.docx", goes along as the hint documents.py uses to
    tell kinds of plain text apart, like .csv and .txt. outline.py is
    imported here, when the first outline is read, instead of when Groot
    starts, so the rest of Groot works even while it is missing. Raises
    Refused if outline.py is not there, and OutlineFailed with outline.py's
    own sentence when the outline could not be read.
    """
    try:
        outline = importlib.import_module("deadline_agent.outline")
    except ModuleNotFoundError as error:
        if error.name != "deadline_agent.outline":
            raise  # outline.py is there, but something it imports is missing
        raise Refused(503, READER_MISSING) from None
    try:
        return outline.extract_items(data, filename=filename, removed=removed)
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
        calendars.session_info(upload.session)
    except ValueError:
        raise Refused(400, "Choose your university and session, then try again.") from None
    classes = _read_timetable(upload)
    notes = [] if classes is None else ["Your timetable was read, so tutorial days come from it."]

    items, outlines = [], []
    for file in upload.outlines:
        found, result = _read_outline(file, read)
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
    if calendars.session_info(upload.session)["university"] != "uts":
        raise Refused(
            400,
            "Groot can only read UTS timetables so far. Remove the timetable, then try again. "
            f"Nothing was sent to {model_choice.ai_name()}.",
        )
    try:
        return timetable.read_timetable(upload.timetable.data, upload.session)
    except ValueError as error:  # its messages are written for the student
        raise Refused(
            400,
            f"Your timetable could not be used. {error} Remove it or choose the right file, "
            f"then try again. Nothing was sent to {model_choice.ai_name()}.",
        ) from None


def _read_outline(file: UploadedFile, read: OutlineReader) -> tuple[list[ExtractedItem], dict]:
    """The items found in one outline, and a short result for the page.

    A problem with this outline becomes one sentence in the result, so the
    other outlines are still read and nothing found so far is lost.
    """
    removed = []  # the kinds of sensitive detail taken out of this outline before it was sent
    try:
        found = read(file.data, file.name, removed)
    except OutlineFailed as error:
        return [], {"file": file.name, "status": "error", "message": str(error)}
    except Refused:
        raise  # a problem with the whole preview, like the outline reader missing
    except Exception:
        # A bug, or a surprise from Gemini's library. The stack trace goes to
        # the window where Groot runs, never to the page.
        logger.exception("Reading the outline %s failed", file.name)
        return [], {"file": file.name, "status": "error", "message": UNEXPECTED_PROBLEM}
    if not found:
        message = "No assessments were found in this outline."
    else:
        message = f"Found {tools._plural(len(found), 'assessment item')}."
    if removed:
        kinds = privacy.describe(list(dict.fromkeys(removed)))
        message += (
            f" Before sending it to {model_choice.ai_name()}, Groot took out what looked like {kinds}, "
            "so check this outline's rows carefully."
        )
    return found, {"file": file.name, "status": "success", "message": message}


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
