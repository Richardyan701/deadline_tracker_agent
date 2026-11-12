"""Read the outline drop box's upload into memory. Nothing is ever written to disk.

FastAPI's usual way to receive files (UploadFile) keeps only the first 1 MB
of each file in memory and writes the rest to a temporary file on disk.
Outlines and timetables are the student's own documents, so this module
reads the upload with the same python-multipart parser underneath, keeps
every byte in memory, and stops as soon as something is too big.

The drop box page sends these form fields:

    outlines    1 to 8 files, each at most 10 MB, of any kind documents.py reads
    timetable   optional, one PDF file of at most 10 MB
    canvas_url  optional text, the student's Canvas calendar feed link
    session     text, the session code, like "SPR2026"

What each outline really is comes from its bytes (documents.detect_kind),
and its name is only a hint. Every file is checked before any outline is
sent to Gemini, so a wrong file never wastes a request.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from python_multipart import MultipartParser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header

from deadline_agent import documents

from . import Refused

MAX_FILE_BYTES = documents.MAX_FILE_BYTES  # 10 MB for each file
MAX_OUTLINES = 8
MAX_TEXT_BYTES = 2048  # the Canvas link and the session code are short
# No proper upload can be bigger than 8 outlines and a timetable at their
# biggest, plus a little room for the lines between the parts of the form.
MAX_UPLOAD_BYTES = (MAX_OUTLINES + 1) * MAX_FILE_BYTES + 64 * 1024

# How many of each field one upload may have
FILE_FIELDS = {"outlines": MAX_OUTLINES, "timetable": 1}
TEXT_FIELDS = {"canvas_url": 1, "session": 1}

TOO_BIG = (
    f"The upload is too big. Each file can be at most {MAX_FILE_BYTES // (1024 * 1024)} MB, "
    f"and at most {MAX_OUTLINES} outlines can be read at a time."
)
TOO_MANY = {
    "outlines": f"At most {MAX_OUTLINES} outlines can be read at a time. Remove some, then try again.",
    "timetable": "Only one timetable can be added at a time.",
}


@dataclass
class UploadedFile:
    """One uploaded file: an outline of any kind Groot reads, or the timetable PDF."""

    name: str  # the file's name on the student's computer, a hint for documents.py and shown back to them
    data: bytes


@dataclass
class Upload:
    """Everything the drop box sent, checked and ready to use."""

    outlines: list[UploadedFile]  # 1 to 8 of them
    timetable: UploadedFile | None
    canvas_url: str  # "" when none was given. It works like a password, so never log it.
    session: str  # not checked yet, preview.py checks it is a real session


async def read_upload(content_type: str, body: AsyncIterator[bytes]) -> Upload:
    """Read the drop box's form into memory and check it.

    content_type is the request's Content-Type header, which holds the
    "boundary" text that separates the parts of the form. body gives the
    request's bytes a piece at a time. Raises Refused, with a reason the
    student can act on, if anything is missing or too big, an outline is a
    kind of file Groot cannot read, or the timetable is not a PDF.
    """
    _, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if not boundary:
        raise Refused(400, "The upload was not a proper form, so it was not read.")

    collector = _PartCollector()
    received = 0
    try:
        parser = MultipartParser(boundary, collector.callbacks())
        async for chunk in body:
            received += len(chunk)
            if received > MAX_UPLOAD_BYTES:
                raise Refused(413, TOO_BIG)
            parser.write(chunk)
        parser.finalize()
    except FormParserError:  # the form's layout is broken
        raise Refused(400, "The upload could not be read, so please try again.") from None
    if not collector.finished:
        raise Refused(400, "The upload was cut off before the end, so please try again.")
    return _checked(collector.parts)


@dataclass
class _Part:
    """One part of the form while it is being read: a file or a text field."""

    field: str  # the form field, like "outlines"
    filename: str | None  # None for a text field
    data: bytearray


class _PartCollector:
    """The functions python-multipart calls while it reads the form.

    Each part is collected into memory. A part that is not expected, or that
    grows past its limit, stops the reading straight away by raising Refused.
    """

    def __init__(self) -> None:
        self.parts: list[_Part] = []
        self.finished = False  # True once the form's closing line has been read
        self._header_name = b""
        self._header_value = b""
        self._disposition = b""  # the part's Content-Disposition header, which names its field

    def callbacks(self) -> dict:
        return {
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_end": self.on_end,
        }

    # A header can arrive in several pieces, so the pieces are joined up first
    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        if self._header_name.lower() == b"content-disposition":
            self._disposition = self._header_value
        self._header_name = self._header_value = b""

    def on_headers_finished(self) -> None:
        """A new part starts. Check it is a field we expect, and not one too many."""
        _, options = parse_options_header(self._disposition)
        self._disposition = b""
        field = options.get(b"name", b"").decode("utf-8", "replace")
        filename = options.get(b"filename")
        expected = FILE_FIELDS if filename is not None else TEXT_FIELDS
        if field not in expected:
            raise Refused(400, "The upload had a part Groot does not expect, so it was not read.")
        if sum(part.field == field for part in self.parts) == expected[field]:
            raise Refused(400, TOO_MANY.get(field, "The upload had the same field twice, so it was not read."))
        # Browsers send file names as UTF-8. "replace" keeps a broken name readable instead of failing.
        name = None if filename is None else filename.decode("utf-8", "replace")
        self.parts.append(_Part(field, name, bytearray()))

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        part = self.parts[-1]
        part.data += data[start:end]
        if part.filename is None and len(part.data) > MAX_TEXT_BYTES:
            raise Refused(400, "Some text in the upload is too long, so it was not read.")
        if part.filename is not None and len(part.data) > MAX_FILE_BYTES:
            raise Refused(413, f"{part.filename} is bigger than 10 MB, so nothing was read.")

    def on_end(self) -> None:
        self.finished = True


def _checked(parts: list[_Part]) -> Upload:
    """The upload, once the rules that need the whole form have been checked."""
    files = {field: [] for field in FILE_FIELDS}
    texts = {}
    for part in parts:
        if part.filename is None:
            try:
                texts[part.field] = part.data.decode("utf-8")
            except UnicodeDecodeError:
                raise Refused(400, "Some text in the upload is not readable, so it was not read.") from None
        else:
            files[part.field].append(UploadedFile(part.filename, bytes(part.data)))

    if not files["outlines"]:
        raise Refused(400, "Add at least one subject outline, then try again.")
    for outline in files["outlines"]:
        try:
            documents.detect_kind(outline.data, outline.name)
        except documents.DocumentError as error:
            raise Refused(400, f"{outline.name}: {error} Nothing was sent to Gemini.") from None
    for timetable in files["timetable"]:
        # The timetable reader only reads the PDF export of the UTS timetable, and every PDF starts with %PDF-
        if not timetable.data.startswith(documents.PDF_START):
            raise Refused(400, f"{timetable.name} is not a PDF, so nothing was read. Check you chose the right file.")
    if "session" not in texts:
        raise Refused(400, "Choose a session, then try again.")

    timetable = files["timetable"][0] if files["timetable"] else None
    return Upload(files["outlines"], timetable, texts.get("canvas_url", "").strip(), texts["session"])
