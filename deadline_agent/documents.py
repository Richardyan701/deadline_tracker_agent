"""Turns an uploaded outline file into what Gemini should receive.

A PDF or an image (PNG, JPEG or WEBP) goes to Gemini as it is. Every other
kind of file is read here and turned into plain text. Table rows stay on one
line each, with their cells separated by " | ", because assessment tables
matter. Slides get "Slide N" headings and sheets get "Sheet: name" headings.

What a file really is comes from its bytes: the first few bytes, and for
Word, PowerPoint, Excel and OpenDocument files (which are zip files) the list
of parts inside the zip. The file name is only a hint. It is needed for kinds
of text that look the same inside, like .csv, .md and .txt.

Nothing inside a file is ever run. Files with macros are refused, and size
limits stop files that would blow up into something huge when unpacked.
"""

import codecs
import csv
import io
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from html.parser import HTMLParser
from pathlib import Path

import docx
import olefile
import openpyxl
import pptx
import xlrd
from defusedxml import ElementTree as SafeXML  # an XML reader that refuses tricks like the "billion laughs"
from pypdf import PasswordType, PdfReader

# ---------- limits ----------

# The drop box takes files of up to 10 MB.
MAX_FILE_BYTES = 10 * 1024 * 1024

# Word, PowerPoint, Excel and OpenDocument files are zip files. A tiny zip can
# unpack into gigabytes (a "zip bomb"), so the parts inside are counted first.
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024
MAX_ZIP_PARTS = 1000

# Spreadsheets are read row by row until one of these limits is reached.
MAX_ROWS = 5_000
MAX_CELLS = 50_000

# The most text sent to Gemini for one file.
MAX_TEXT_CHARS = 200_000

# How long LibreOffice gets to turn an old .doc or .ppt file into .docx or .pptx.
CONVERT_TIMEOUT_SECONDS = 60

# ---------- what Groot can read ----------

# Each kind of file, with the endings its names usually have.
FORMATS = [
    ("PDF", [".pdf"]),
    ("Word", [".docx", ".doc"]),
    ("PowerPoint", [".pptx", ".ppt"]),
    ("Excel", [".xlsx", ".xls"]),
    ("OpenDocument", [".odt", ".odp", ".ods"]),
    ("CSV", [".csv"]),
    ("text", [".txt", ".md"]),
    ("web page", [".html", ".htm"]),
    ("image", [".png", ".jpg", ".jpeg", ".webp"]),
]

SUPPORTED_EXTENSIONS = tuple(ending for _, endings in FORMATS for ending in endings)

# For the web page's file picker: <input type="file" accept="...">
HTML_ACCEPT = ",".join(SUPPORTED_EXTENSIONS)


def _list_formats() -> str:
    """For example "PDF (.pdf), Word (.docx, .doc), ... or image (.png, .jpg, .jpeg, .webp)"."""
    names = [f"{name} ({', '.join(endings)})" for name, endings in FORMATS]
    return ", ".join(names[:-1]) + " or " + names[-1]


FORMAT_LIST = _list_formats()


def describe_supported() -> str:
    """One sentence that lists every kind of file Groot can read, for the web page."""
    return f"Groot can read {FORMAT_LIST} files."


# ---------- errors ----------


class DocumentError(Exception):
    """The file cannot be used. The message is safe to show the student."""


EMPTY_MESSAGE = f"This file is empty, so please upload your outline as a {FORMAT_LIST} file."
UNKNOWN_MESSAGE = f"Groot cannot read this kind of file, so please upload your outline as a {FORMAT_LIST} file."
LOCKED_MESSAGE = (
    f"This file is locked with a password, so please remove the password and upload it as a {FORMAT_LIST} file."
)
TOO_BIG_MESSAGE = "This file is bigger than 10 MB, so please upload a smaller copy, for example a PDF."
ZIP_BOMB_MESSAGE = "This file holds far too much data inside, so Groot did not open it."
MACRO_MESSAGE = (
    "This file has macros, which Groot never opens, so please save it as .docx, .xlsx, .pptx or PDF and try again."
)
DAMAGED_MESSAGE = (
    "Groot could not read this file because it seems to be damaged, so please save a new copy and upload that."
)
NO_TEXT_MESSAGE = "Groot found no text in this file, so if it is a scan, please upload it as a PDF or an image."
OLD_OFFICE_MESSAGE = "This is an old Word/PowerPoint file. Save it as .docx, .pptx or PDF and try again."
CONVERT_FAILED_MESSAGE = (
    "LibreOffice could not convert this old Word/PowerPoint file, so please save it as .docx, .pptx or PDF"
    " and try again."
)
CONVERT_TIMEOUT_MESSAGE = (
    "LibreOffice took too long to convert this old Word/PowerPoint file, so please save it as .docx, .pptx or PDF"
    " and try again."
)

# Added to the text when Groot stops reading early, so Gemini knows something is missing.
TEXT_CUT_NOTE = f"[Groot stopped reading here, because it sends at most {MAX_TEXT_CHARS:,} characters of a file.]"
ROWS_CUT_NOTE = (
    f"[Groot stopped reading here, because it reads at most {MAX_ROWS:,} rows and {MAX_CELLS:,} cells"
    " of a spreadsheet.]"
)


# ---------- what read_document gives back ----------


@dataclass(frozen=True)
class Document:
    """One outline file, ready for Gemini.

    A PDF or an image goes to Gemini as it is: mime_type says what it is and
    data holds the file. Every other kind goes as the text read out of it, and
    then mime_type is "".
    """

    kind: str  # what the file really is, for example "docx"
    mime_type: str = ""
    data: bytes = b""
    text: str = ""


# ---------- working out what a file really is ----------

# The first bytes of each kind of file.
PDF_START = b"%PDF-"
PNG_START = b"\x89PNG\r\n\x1a\n"
JPEG_START = b"\xff\xd8\xff"
ZIP_START = b"PK\x03\x04"
OLE_START = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old Office files, and new ones locked with a password
UTF16_STARTS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)  # text saved as UTF-16 starts with one of these

# The kinds Gemini reads itself, with their mime types.
FILE_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}

# Names that say the file has macros. They are refused whatever is inside.
MACRO_ENDINGS = {".docm", ".xlsm", ".pptm"}

# Plain text has nothing special inside, so its kind comes from the name.
TEXT_KINDS = {".txt": "txt", ".md": "md", ".csv": "csv", ".html": "html", ".htm": "html"}

# The type of the main part of each kind of Office file, as listed in [Content_Types].xml.
OFFICE_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
}

# Words in [Content_Types].xml that mean an Office file holds macros.
MACRO_TYPES = ("macroenabled", "vbaproject", "macrosheet")

# What an OpenDocument file says it is, in the part called "mimetype".
OPENDOCUMENT_TYPES = {
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
}
MANIFEST = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}"


def _detect_kind(data: bytes, ending: str) -> str:
    """What the file really is, for example "docx", from its bytes. ending (like ".csv") is only a hint."""
    if not data:
        raise DocumentError(EMPTY_MESSAGE)
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError(TOO_BIG_MESSAGE)
    if ending in MACRO_ENDINGS:
        raise DocumentError(MACRO_MESSAGE)
    if data.startswith(PDF_START):
        return "pdf"
    if data.startswith(PNG_START):
        return "png"
    if data.startswith(JPEG_START):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(ZIP_START):
        return _zip_kind(data)
    if data.startswith(OLE_START):
        return _old_office_kind(data)
    # Text never has a zero byte in it, unless it is saved as UTF-16.
    if data.startswith(UTF16_STARTS) or b"\0" not in data:
        return _text_kind(data, ending)
    raise DocumentError(UNKNOWN_MESSAGE)


def _zip_kind(data: bytes) -> str:
    """docx, pptx, xlsx, odt, odp or ods, from the parts inside the zip."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = archive.infolist()
        # Python never unpacks more than the size each part declares, so the sum is a safe limit.
        if len(parts) > MAX_ZIP_PARTS or sum(part.file_size for part in parts) > MAX_UNZIPPED_BYTES:
            raise DocumentError(ZIP_BOMB_MESSAGE)
        if any(part.flag_bits & 1 for part in parts):  # this bit means the part is locked with a password
            raise DocumentError(LOCKED_MESSAGE)
        names = archive.namelist()
        if "mimetype" in names:  # OpenDocument files name their kind in this part
            return _opendocument_kind(archive)
        if "[Content_Types].xml" in names:  # Word, PowerPoint and Excel files list their parts here
            return _office_kind(archive)
    raise DocumentError(UNKNOWN_MESSAGE)


def _office_kind(archive: zipfile.ZipFile) -> str:
    """docx, pptx or xlsx, from [Content_Types].xml. Files with macros are refused."""
    listing = SafeXML.fromstring(archive.read("[Content_Types].xml"))
    content_types = [entry.get("ContentType", "") for entry in listing]
    declares_macros = any(word in content_type.lower() for content_type in content_types for word in MACRO_TYPES)
    has_macros = any(name.lower().endswith("vbaproject.bin") for name in archive.namelist())
    if declares_macros or has_macros:
        raise DocumentError(MACRO_MESSAGE)
    for kind, main_type in OFFICE_TYPES.items():
        if main_type in content_types:
            return kind
    raise DocumentError(UNKNOWN_MESSAGE)


def _opendocument_kind(archive: zipfile.ZipFile) -> str:
    """odt, odp or ods, from the part called "mimetype"."""
    kind = OPENDOCUMENT_TYPES.get(archive.read("mimetype").decode("ascii", errors="replace").strip())
    if kind is None:
        raise DocumentError(UNKNOWN_MESSAGE)
    manifest = SafeXML.fromstring(archive.read("META-INF/manifest.xml"))
    if manifest.find(f".//{MANIFEST}encryption-data") is not None:  # saved with a password
        raise DocumentError(LOCKED_MESSAGE)
    return kind


def _old_office_kind(data: bytes) -> str:
    """doc, ppt or xls, from the names of the parts (streams) inside an old Office file."""
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        if ole.exists("EncryptedPackage"):  # a .docx, .xlsx or .pptx locked with a password
            raise DocumentError(LOCKED_MESSAGE)
        if ole.exists("Macros") or ole.exists("_VBA_PROJECT_CUR"):  # where old Word and Excel files keep macros
            raise DocumentError(MACRO_MESSAGE)
        if ole.exists("WordDocument"):
            header = ole.openstream("WordDocument").read(12)
            if int.from_bytes(header[10:12], "little") & 0x0100:  # Word's "locked with a password" flag
                raise DocumentError(LOCKED_MESSAGE)
            return "doc"
        if ole.exists("PowerPoint Document"):
            return "ppt"
        if ole.exists("Workbook") or ole.exists("Book"):
            return "xls"
    raise DocumentError(UNKNOWN_MESSAGE)


def _text_kind(data: bytes, ending: str) -> str:
    """csv, md, html or txt. The name decides, and with no useful name a web page is told by its start."""
    if ending in TEXT_KINDS:
        return TEXT_KINDS[ending]
    start = _decode(data[:1000]).lstrip().lower()
    return "html" if start.startswith(("<!doctype html", "<html")) else "txt"


# ---------- Word and PowerPoint ----------

# Word (w:) and PowerPoint (a:) keep text the same way: paragraphs (p) hold
# pieces of text (t), and tables have rows (tr) made of cells (tc).
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
OFFICE_PARAGRAPHS = {W + "p", A + "p"}
OFFICE_ROWS = {W + "tr", A + "tr"}
OFFICE_CELLS = {W + "tc", A + "tc"}
OFFICE_TEXT = {W + "t", A + "t"}
OFFICE_GAPS = {W + "tab", W + "br", W + "cr", A + "br"}  # tabs and line breaks
# Office keeps a second copy of some shapes, like text boxes, for old versions. Reading it would double their text.
OFFICE_SECOND_COPY = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _office_lines(element) -> list[str]:
    """Each paragraph and each table row inside a Word or PowerPoint element, as one line."""
    lines = []
    for child in element:
        if child.tag in OFFICE_PARAGRAPHS:
            lines.append(_office_words(child))
        elif child.tag in OFFICE_ROWS:
            cells = [_tidy(" ".join(_office_lines(cell))) for cell in child if cell.tag in OFFICE_CELLS]
            if any(cells):
                lines.append(" | ".join(cells))
        elif child.tag != OFFICE_SECOND_COPY:
            lines += _office_lines(child)  # tables, sections, content controls, shapes and so on
    return lines


def _office_words(element) -> str:
    """The text of one paragraph, including any text box inside it."""
    if element.tag in OFFICE_TEXT:
        return element.text or ""
    if element.tag in OFFICE_GAPS:
        return " "
    if element.tag == OFFICE_SECOND_COPY:
        return ""
    words = "".join(_office_words(child) for child in element)
    return f" {words} " if element.tag in OFFICE_PARAGRAPHS else words  # keeps paragraphs in a text box apart


def _read_docx(data: bytes) -> str:
    """Every paragraph and table row of a Word file, in order."""
    return _join_lines(_office_lines(docx.Document(io.BytesIO(data)).element.body))


def _read_pptx(data: bytes) -> str:
    """The text and tables of every slide under a "Slide N" heading, then its speaker notes."""
    lines = []
    for number, slide in enumerate(pptx.Presentation(io.BytesIO(data)).slides, start=1):
        lines.append(f"Slide {number}")
        lines += _office_lines(slide.element)
        notes = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
        if notes is not None and notes.text.strip():
            lines.append(f"Speaker notes: {notes.text}")
    return _join_lines(lines)


# ---------- OpenDocument (.odt, .odp, .ods) ----------

OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
PRESENTATION = "{urn:oasis:names:tc:opendocument:xmlns:presentation:1.0}"
ODF_PARAGRAPHS = {TEXT + "p", TEXT + "h"}  # paragraphs and headings
ODF_ROW = TABLE + "table-row"
ODF_CELLS = {TABLE + "table-cell", TABLE + "covered-table-cell"}
ODF_GAPS = {TEXT + "s", TEXT + "tab", TEXT + "line-break"}  # spaces, tabs and line breaks
# Left out: old text kept for tracked changes, comments, slide numbers, and speaker notes (read on their own).
ODF_SKIP = {TEXT + "tracked-changes", OFFICE + "annotation", TEXT + "page-number", PRESENTATION + "notes"}


def _odf_lines(element) -> list[str]:
    """Each paragraph and each table row inside an OpenDocument element, as one line."""
    lines = []
    for child in element:
        if child.tag in ODF_PARAGRAPHS:
            lines.append(_odf_words(child))
        elif child.tag == ODF_ROW:
            cells = [_tidy(" ".join(_odf_lines(cell))) for cell in child if cell.tag in ODF_CELLS]
            if any(cells):
                lines.append(" | ".join(cells))
        elif child.tag not in ODF_SKIP:
            lines += _odf_lines(child)  # lists, sections, tables, frames and so on
    return lines


def _odf_words(element) -> str:
    """The text of one paragraph, including spans, links and frames inside it."""
    words = [element.text or ""]
    for child in element:
        if child.tag in ODF_GAPS:
            words.append(" ")
        elif child.tag in ODF_PARAGRAPHS:
            words.append(f" {_odf_words(child)} ")  # a paragraph inside a frame
        elif child.tag not in ODF_SKIP:
            words.append(_odf_words(child))
        words.append(child.tail or "")
    return "".join(words)


def _odf_body(data: bytes, kind: str):
    """The part of content.xml that holds the text, slides or sheets ("text", "presentation" or "spreadsheet")."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        content = SafeXML.fromstring(archive.read("content.xml"))
    return content.find(f"{OFFICE}body/{OFFICE}{kind}")


def _read_odt(data: bytes) -> str:
    """Every paragraph and table row of an OpenDocument text file, in order."""
    return _join_lines(_odf_lines(_odf_body(data, "text")))


def _read_odp(data: bytes) -> str:
    """The text and tables of every slide under a "Slide N" heading, then its speaker notes."""
    lines = []
    for number, page in enumerate(_odf_body(data, "presentation").findall(DRAW + "page"), start=1):
        lines.append(f"Slide {number}")
        lines += _odf_lines(page)
        notes = " ".join(" ".join(_odf_lines(part)) for part in page.findall(PRESENTATION + "notes"))
        if notes.strip():
            lines.append(f"Speaker notes: {notes}")
    return _join_lines(lines)


# ---------- spreadsheets (.xlsx, .xls, .ods, .csv) ----------


def _sheet_lines(sheets) -> list[str]:
    """A "Sheet: name" heading for every sheet, then one line per row with its cells joined by " | ".

    sheets gives (name, rows) pairs, and each row is a list of cell texts.
    Empty rows are skipped. Reading stops after MAX_ROWS rows or MAX_CELLS cells.
    """
    lines, rows_read, cells_read = [], 0, 0
    for name, rows in sheets:
        lines.append(f"Sheet: {name}")
        for row in rows:
            row = [_tidy(cell) for cell in row]
            while row and not row[-1]:  # empty cells at the end of a row add nothing
                row.pop()
            if not row:
                continue
            rows_read += 1
            cells_read += len(row)
            if rows_read > MAX_ROWS or cells_read > MAX_CELLS:
                lines.append(ROWS_CUT_NOTE)
                return lines
            lines.append(" | ".join(row))
    return lines


def _cell_text(value, number_format) -> str:
    """One spreadsheet value as text. Dates become "YYYY-MM-DD" and percentages keep their % sign."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d" if value.time() == time(0) else "%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, (int, float)):
        if "%" in (number_format or ""):  # 0.1 shown as 10%
            return f"{round(value * 100, 6):g}%"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))  # 10.0 becomes 10
    return str(value)


def _read_xlsx(data: bytes) -> str:
    """Every sheet of an Excel file. data_only=True gives the values Excel saved, never the formulas."""
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return _join_lines(_sheet_lines((sheet.title, _xlsx_rows(sheet)) for sheet in workbook.worksheets))
    finally:
        workbook.close()


def _xlsx_rows(sheet):
    """Each row of one Excel sheet, as cell texts."""
    sheet.reset_dimensions()  # some programs save a wrong sheet size, which would hide rows
    for row in sheet.iter_rows():
        yield [_cell_text(cell.value, cell.number_format) for cell in row]


def _read_xls(data: bytes) -> str:
    """Every sheet of an old Excel file. xlrd gives the values Excel saved, never the formulas."""
    try:
        # formatting_info=True tells dates and percentages apart from plain numbers.
        # xlrd writes notes to its log, so they go to a string that is thrown away.
        book = xlrd.open_workbook(file_contents=data, formatting_info=True, logfile=io.StringIO())
    except xlrd.XLRDError as error:
        if str(error) == "Workbook is encrypted":
            raise DocumentError(LOCKED_MESSAGE) from error
        raise
    return _join_lines(_sheet_lines((sheet.name, _xls_rows(book, sheet)) for sheet in book.sheets()))


def _xls_rows(book, sheet):
    """Each row of one old Excel sheet, as cell texts."""
    for number in range(sheet.nrows):
        yield [_xls_cell_text(book, cell) for cell in sheet.row(number)]


def _xls_cell_text(book, cell) -> str:
    """One cell of an old Excel file as text."""
    if cell.ctype == xlrd.XL_CELL_DATE:
        return _cell_text(xlrd.xldate_as_datetime(cell.value, book.datemode), None)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return _cell_text(bool(cell.value), None)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value, "#ERROR")
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        number_format = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
        return _cell_text(cell.value, number_format)
    return _cell_text(cell.value, None)  # text, or "" for an empty cell


def _read_ods(data: bytes) -> str:
    """Every sheet of an OpenDocument spreadsheet, with each cell as it is shown (never its formula)."""
    sheets = _odf_body(data, "spreadsheet").findall(TABLE + "table")
    return _join_lines(_sheet_lines((sheet.get(TABLE + "name", ""), _ods_rows(sheet)) for sheet in sheets))


def _ods_rows(sheet):
    """Each row of one OpenDocument sheet.

    A run of identical cells or rows is saved once with a repeat count.
    LibreOffice saves the empty cells up to the right edge of the sheet like
    that, about 16,000 of them, so empty cells at the end of a row are dropped
    before anything is written out. Empty rows are never repeated, and the
    other repeats stop at the limits.
    """
    for row in sheet.iter(ODF_ROW):
        runs = [
            (" ".join(_odf_lines(cell)), int(cell.get(TABLE + "number-columns-repeated", "1")))
            for cell in row
            if cell.tag in ODF_CELLS
        ]
        while runs and not runs[-1][0].strip():
            runs.pop()
        cells = []
        for text, repeat in runs:
            cells += [text] * min(repeat, MAX_CELLS - len(cells))
        repeat = int(row.get(TABLE + "number-rows-repeated", "1")) if cells else 1
        for _ in range(min(repeat, MAX_ROWS)):
            yield cells


def _read_csv(data: bytes) -> str:
    """A CSV file is one sheet."""
    rows = csv.reader(io.StringIO(_decode(data), newline=""))
    return _join_lines(_sheet_lines([("1", rows)]))


# ---------- text and web pages ----------


def _read_text(data: bytes) -> str:
    """A .txt or .md file, as it is."""
    return _decode(data)


# Tags whose text a browser never shows.
HTML_HIDDEN = {"script", "style", "template", "noscript"}
# Tags that start a new line.
HTML_BLOCKS = {
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tbody", "tfoot", "thead", "title", "ul",
}


class _WebPageText(HTMLParser):
    """Collects the text a browser would show, with each table row on one line.

    Scripts and styles are skipped, and &amp; and the like become characters.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pieces = []  # the text so far, joined at the end
        self.hidden = 0  # how many script or style tags we are inside
        self.in_row = False  # inside a table row, where everything stays on one line
        self.cells = 0  # cells so far in this row

    def handle_starttag(self, tag, attrs):
        if tag in HTML_HIDDEN:
            self.hidden += 1
        elif tag == "tr":
            self.pieces.append("\n")
            self.in_row, self.cells = True, 0
        elif tag in ("td", "th"):
            if self.cells:
                self.pieces.append(" | ")
            self.cells += 1
        elif tag in HTML_BLOCKS:
            self._break()

    def handle_endtag(self, tag):
        if tag in HTML_HIDDEN:
            self.hidden = max(self.hidden - 1, 0)
        elif tag in ("tr", "table"):
            self.in_row = False
            self.pieces.append("\n")
        elif tag in HTML_BLOCKS:
            self._break()

    def handle_data(self, data):
        if not self.hidden:
            self.pieces.append(data.replace("\n", " "))  # line breaks in the HTML source are only spaces

    def _break(self):
        """A new line, or only a space inside a table row so the row stays together."""
        self.pieces.append(" " if self.in_row else "\n")


def _read_html(data: bytes) -> str:
    """The readable text of a web page."""
    page = _WebPageText()
    page.feed(_decode(data))
    page.close()
    return _join_lines("".join(page.pieces).split("\n"))


# ---------- old Word and PowerPoint files (.doc, .ppt) ----------


def _read_doc(data: bytes) -> str:
    return _read_docx(_converted(data, "doc", "docx"))


def _read_ppt(data: bytes) -> str:
    return _read_pptx(_converted(data, "ppt", "pptx"))


# Settings for a new LibreOffice profile that switch off every kind of macro
# (Basic, Python and the rest), whatever is inside the file.
NO_MACROS_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
</item>
</oor:items>
"""


def _converted(data: bytes, old: str, new: str) -> bytes:
    """The file turned from .doc into .docx (or .ppt into .pptx) by LibreOffice, if it is installed."""
    program = shutil.which("soffice") or shutil.which("libreoffice")
    if program is None:
        raise DocumentError(OLD_OFFICE_MESSAGE)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        folder = Path(folder)
        source = folder / f"outline.{old}"  # a fixed name, so nothing from the student's file name reaches the command
        source.write_bytes(data)
        # A new LibreOffice profile with macros switched off. It also works while LibreOffice is open.
        profile = folder / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(NO_MACROS_SETTINGS, encoding="utf-8")
        command = [
            program,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--convert-to",
            new,
            "--outdir",
            str(folder),
            str(source),
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=CONVERT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise DocumentError(CONVERT_TIMEOUT_MESSAGE) from error
        except OSError as error:  # LibreOffice could not be started
            raise DocumentError(CONVERT_FAILED_MESSAGE) from error
        # LibreOffice says it succeeded even when it fails, so the new file is the only proof.
        result = folder / f"outline.{new}"
        if not result.is_file():
            raise DocumentError(CONVERT_FAILED_MESSAGE)
        converted = result.read_bytes()
    if _detect_kind(converted, "") != new:  # the same checks as an upload: size, zip bomb and macros
        raise DocumentError(CONVERT_FAILED_MESSAGE)
    return converted


# ---------- small helpers ----------


def _decode(data: bytes) -> str:
    """Text from bytes. UTF-16 is told by its first two bytes. Anything else is read as UTF-8."""
    if data.startswith(UTF16_STARTS):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")  # a character that is not UTF-8 becomes "�"


def _tidy(text: str) -> str:
    """One line of text with single spaces."""
    return " ".join(text.split())


def _join_lines(lines) -> str:
    """The lines as one text, tidied, with empty lines left out."""
    return "\n".join(line for line in map(_tidy, lines) if line)


def _pdf_needs_password(data: bytes) -> bool:
    """True if the PDF cannot even be opened without a password.

    Many PDFs are locked only against editing or printing. They open without a
    password, so Gemini can still read them, and they are fine.
    """
    if b"/Encrypt" not in data:  # every locked PDF has an /Encrypt entry
        return False
    reader = PdfReader(io.BytesIO(data))
    return reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED


# ---------- reading one file ----------

# The reader for each kind of file that is sent as text.
READERS = {
    "docx": _read_docx,
    "doc": _read_doc,
    "odt": _read_odt,
    "pptx": _read_pptx,
    "ppt": _read_ppt,
    "odp": _read_odp,
    "xlsx": _read_xlsx,
    "xls": _read_xls,
    "ods": _read_ods,
    "csv": _read_csv,
    "txt": _read_text,
    "md": _read_text,
    "html": _read_html,
}


def read_document(data: bytes, filename: str | None = None) -> Document:
    """Work out what kind of file this is and turn it into a Document for Gemini.

    filename (for example "33130.docx") is only a hint. It tells apart kinds of
    plain text, like .csv and .txt, which have nothing special in their bytes.

    Raises DocumentError, with a message for the student, when the file cannot be used.
    """
    ending = Path(filename).suffix.lower() if filename else ""
    try:
        kind = _detect_kind(data, ending)
        if kind in FILE_TYPES:
            if kind == "pdf" and _pdf_needs_password(data):
                raise DocumentError(LOCKED_MESSAGE)
            return Document(kind, mime_type=FILE_TYPES[kind], data=data)
        text = READERS[kind](data)
    except DocumentError:
        raise
    except Exception as error:  # every library has its own errors for a damaged file
        raise DocumentError(DAMAGED_MESSAGE) from error
    if not text.strip():
        raise DocumentError(NO_TEXT_MESSAGE)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n" + TEXT_CUT_NOTE
    return Document(kind, text=text)
