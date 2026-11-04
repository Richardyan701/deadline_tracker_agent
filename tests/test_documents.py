"""Tests for the document reader (deadline_agent/documents.py).

No API key, no internet and no LibreOffice needed. Every file is built inside
the tests: Word, PowerPoint and Excel files with python-docx, python-pptx and
openpyxl, PDFs with pypdf, pictures with Pillow, and OpenDocument files and
the container of old Office files by hand. The one exception is
tests/fixtures/assessments.xls, a 6.5 KB old Excel file, because no
maintained Python library can write .xls files.
"""

import io
import struct
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import docx
import openpyxl
import pptx
import pytest
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from PIL import Image
from pptx.util import Inches
from pypdf import PdfWriter

from deadline_agent import documents
from deadline_agent.documents import DocumentError

FIXTURES = Path(__file__).parent / "fixtures"

# tests/fixtures/assessments.xls was made once with LibreOffice from an openpyxl
# workbook holding exactly these cells. B2 to B4 have the format "0%", C2 is a
# date and B4 is the formula =B2+B3, saved with its value 0.6.
XLS_TEXT = """Sheet: Assessments
Task | Weight | Due | Week
Skills Test 1 | 10% | 2026-09-04 | 2
Final exam | 50% | | Exam period
Total | 60%
Group work | TRUE
Sheet: Notes
Check Canvas for details"""


# ---------- helpers ----------


def read(data: bytes, filename=None) -> documents.Document:
    return documents.read_document(data, filename)


def text_of(data: bytes, filename=None) -> str:
    return read(data, filename).text


def refusal(data: bytes, filename=None) -> DocumentError:
    """The error read_document raises for this file."""
    with pytest.raises(DocumentError) as caught:
        read(data, filename)
    return caught.value


def saved(thing) -> bytes:
    """The bytes of a python-docx, python-pptx or openpyxl file."""
    out = io.BytesIO()
    thing.save(out)
    return out.getvalue()


def zip_file(parts: dict) -> bytes:
    """A zip file holding these parts (name -> text or bytes)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in parts.items():
            # OpenDocument keeps its "mimetype" part unpacked, so programs can read it straight away
            archive.writestr(name, content, zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue()


def zip_with(data: bytes, changes: dict) -> bytes:
    """A copy of a zip file with some parts changed or added.

    Each change is the part's new content, or a function that gets the old content and gives the new one.
    """
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {name: archive.read(name) for name in archive.namelist()}
    for name, change in changes.items():
        parts[name] = change(parts[name]) if callable(change) else change
    return zip_file(parts)


def docx_file(*paragraphs, rows=()) -> bytes:
    """A Word file with these paragraphs, then a table with these rows."""
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if rows:
        table = document.add_table(rows=len(rows), cols=len(rows[0]))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    return saved(document)


# Namespaces for Word XML that python-docx cannot write itself
WORD_EXTRAS = (
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)


def docx_with_body(xml: str) -> bytes:
    """A Word file whose body holds this XML, for things python-docx cannot add, like content controls."""
    document = docx.Document()
    body = document.element.body
    for element in list(parse_xml(f"<w:body {nsdecls('w')} {WORD_EXTRAS}>{xml}</w:body>")):
        body.sectPr.addprevious(element)  # the section settings must stay last
    return saved(document)


def pptx_file() -> bytes:
    """Two slides: a title, text, a table and speaker notes, then a text box inside a group of shapes."""
    presentation = pptx.Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[1])  # "Title and Content"
    first.shapes.title.text = "Assessment summary"
    first.placeholders[1].text = "Quiz 1 is held in week 3"
    table = first.shapes.add_table(2, 2, Inches(1), Inches(5), Inches(6), Inches(1)).table
    for (r, c), value in {(0, 0): "Task", (0, 1): "Weight", (1, 0): "Quiz 1", (1, 1): "10%"}.items():
        table.cell(r, c).text = value
    first.notes_slide.notes_text_frame.text = "Remind students that the quiz is online"
    second = presentation.slides.add_slide(presentation.slide_layouts[6])  # "Blank"
    group = second.shapes.add_group_shape()
    box = group.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    box.text_frame.text = "Final exam in the exam period"
    return saved(presentation)


def xlsx_file() -> bytes:
    """Two sheets with a percentage, a date and a formula. Excel saves a formula's value, so that is added here."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Assessments"
    sheet.append(["Task", "Weight", "Due", "Week"])
    sheet.append(["Skills Test 1", 0.1, datetime(2026, 9, 4), 2])
    sheet.append(["Final exam", 0.5, None, "Exam period"])
    sheet.append(["Total", "=B2+B3"])
    sheet.append(["Group work", True])
    for cell in ["B2", "B3", "B4"]:
        sheet[cell].number_format = "0%"
    workbook.create_sheet("Notes").append(["Check Canvas for details"])
    # openpyxl saves formulas without a value. Excel would save <v>0.6</v>, the value it worked out.
    return zip_with(saved(workbook), {"xl/worksheets/sheet1.xml": lambda xml: xml.replace(b"<v></v>", b"<v>0.6</v>")})


ODF_NAMESPACES = " ".join(
    f'xmlns:{prefix}="urn:oasis:names:tc:opendocument:xmlns:{name}:1.0"'
    for prefix, name in [("office", "office"), ("text", "text"), ("table", "table"), ("draw", "drawing"),
                         ("presentation", "presentation")]
)


def odf_file(kind: str, body: str, locked=False) -> bytes:
    """An OpenDocument file. kind is "text", "presentation" or "spreadsheet", and body is the XML inside it."""
    mimetype = f"application/vnd.oasis.opendocument.{kind}"
    content = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {ODF_NAMESPACES} office:version="1.3">'
        f"<office:body><office:{kind}>{body}</office:{kind}></office:body></office:document-content>"
    )
    # A file saved with a password says how content.xml was encrypted, here in the manifest
    encryption = (
        '<manifest:encryption-data manifest:checksum-type="SHA1/1K" manifest:checksum="AAAA">'
        '<manifest:algorithm manifest:algorithm-name="Blowfish CFB" manifest:initialisation-vector="AAAA"/>'
        "</manifest:encryption-data>"
        if locked
        else ""
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
        f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{mimetype}"/>'
        f'<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml">{encryption}'
        "</manifest:file-entry></manifest:manifest>"
    )
    return zip_file({"mimetype": mimetype, "META-INF/manifest.xml": manifest, "content.xml": content})


def ole_file(streams: dict) -> bytes:
    """A tiny OLE2 "compound file", the container that old .doc, .xls and .ppt files use.

    It works like a small disk inside one file: a 512 byte header, then 512
    byte sectors holding the streams, a directory with their names, and a
    table (the FAT) saying which sector comes next in each stream. Each stream
    is padded to 4096 bytes, the smallest size kept in ordinary sectors, so no
    "mini stream" is needed. Up to three streams fit in the one directory sector.
    """
    sector = 512
    free, end_of_chain, fat_mark, nothing = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
    body, fat, entries = b"", [], []
    for name, data in streams.items():
        data = data.ljust(4096, b"\0")
        data = data.ljust(-(-len(data) // sector) * sector, b"\0")  # whole sectors only
        first, count = len(fat), len(data) // sector
        fat += list(range(first + 1, first + count)) + [end_of_chain]
        entries.append((name, first, len(data)))
        body += data
    directory_sector = len(fat)
    fat.append(end_of_chain)
    fat_sector = len(fat)
    fat.append(fat_mark)

    def entry(name, kind, start, size, right=nothing, child=nothing):
        encoded = (name + "\0").encode("utf-16-le")
        return struct.pack("<64sHBBIII16sIQQIQ", encoded, len(encoded), kind, 1, nothing, right, child,
                           b"\0" * 16, 0, 0, 0, start, size)

    directory = entry("Root Entry", 5, end_of_chain, 0, child=1 if entries else nothing)
    for number, (name, start, size) in enumerate(entries, start=1):
        directory += entry(name, 2, start, size, right=number + 1 if number < len(entries) else nothing)
    header = struct.pack("<8s16sHHHHH6sIIIIIIIII", documents.OLE_START, b"\0" * 16, 0x3E, 3, 0xFFFE, 9, 6,
                         b"\0" * 6, 0, 1, directory_sector, 0, 4096, end_of_chain, 0, end_of_chain, 0)
    header += struct.pack("<109I", fat_sector, *[free] * 108)
    fat_bytes = struct.pack(f"<{sector // 4}I", *(fat + [free] * (sector // 4 - len(fat))))
    return header + body + directory.ljust(sector, b"\0") + fat_bytes


def word_97_header(locked=False) -> bytes:
    """The first bytes of the main stream of an old .doc file. One flag says it is locked with a password."""
    return b"\xec\xa5" + b"\0" * 8 + struct.pack("<H", 0x0100 if locked else 0)


DOC = ole_file({"WordDocument": word_97_header(), "1Table": b""})
PPT = ole_file({"PowerPoint Document": b"", "Current User": b""})


def pdf_file(**lock) -> bytes:
    """A one page PDF, locked with pypdf's encrypt(**lock) when lock is given."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if lock:
        writer.encrypt(**lock)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def picture(kind: str) -> bytes:
    """A tiny real picture, made with Pillow."""
    out = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(out, kind)
    return out.getvalue()


# ---------- what Groot can read ----------


def test_every_supported_ending_is_listed_for_the_web_page():
    assert documents.SUPPORTED_EXTENSIONS == (
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".odp", ".ods",
        ".csv", ".txt", ".md", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp",
    )
    assert documents.HTML_ACCEPT == ",".join(documents.SUPPORTED_EXTENSIONS)
    assert documents.HTML_ACCEPT.startswith(".pdf,.docx,.doc,")


def test_describe_supported_is_one_sentence_with_every_ending():
    sentence = documents.describe_supported()
    assert sentence == (
        "Groot can read PDF (.pdf), Word (.docx, .doc), PowerPoint (.pptx, .ppt), Excel (.xlsx, .xls), "
        "OpenDocument (.odt, .odp, .ods), CSV (.csv), text (.txt, .md), web page (.html, .htm) "
        "or image (.png, .jpg, .jpeg, .webp) files."
    )
    assert all(ending in sentence for ending in documents.SUPPORTED_EXTENSIONS)


# ---------- files Gemini reads itself ----------


@pytest.mark.parametrize(
    "data, kind, mime_type",
    [
        (pdf_file(), "pdf", "application/pdf"),
        (picture("PNG"), "png", "image/png"),
        (picture("JPEG"), "jpeg", "image/jpeg"),
        (picture("WEBP"), "webp", "image/webp"),
    ],
)
def test_pdfs_and_pictures_are_sent_as_they_are(data, kind, mime_type):
    document = read(data, f"outline.{kind}")
    assert document == documents.Document(kind, mime_type=mime_type, data=data)


def test_the_tiny_pretend_pdf_of_the_old_tests_still_goes_through_unchanged():
    data = b"%PDF-1.7\nA pretend outline\n%%EOF"
    assert read(data) == documents.Document("pdf", mime_type="application/pdf", data=data)


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_a_pdf_that_needs_a_password_to_open_is_refused(algorithm):
    error = refusal(pdf_file(user_password="secret", algorithm=algorithm))
    assert str(error) == documents.LOCKED_MESSAGE


def test_a_pdf_locked_only_against_editing_still_goes_to_gemini():
    # Many official PDFs only stop editing or printing. They open without a password.
    data = pdf_file(user_password="", owner_password="owner", algorithm="AES-128")
    assert read(data).mime_type == "application/pdf"


# ---------- the kind comes from the bytes, not the name ----------


@pytest.mark.parametrize(
    "data, name, kind",
    [
        (docx_file("Assignment 1"), "outline.pdf", "docx"),
        (pptx_file(), "outline.docx", "pptx"),
        (xlsx_file(), None, "xlsx"),
        (odf_file("text", "<text:p>Assignment 1</text:p>"), "outline.txt", "odt"),
        (odf_file("presentation", '<draw:page draw:name="1"><text:p>Quiz</text:p></draw:page>'), "outline.ods", "odp"),
        (odf_file("spreadsheet", "<table:table><table:table-row><table:table-cell><text:p>Quiz</text:p>"
                                 "</table:table-cell></table:table-row></table:table>"), "outline.odt", "ods"),
        ((FIXTURES / "assessments.xls").read_bytes(), "outline.doc", "xls"),
        (pdf_file(), "outline.docx", "pdf"),
        (picture("PNG"), "outline.jpg", "png"),
        (picture("JPEG"), "outline.png", "jpeg"),
        (picture("WEBP"), None, "webp"),
        (b"<!DOCTYPE html><p>Quiz in week 3</p>", None, "html"),
        (b"  <HTML><body>Quiz in week 3</body></HTML>", "outline", "html"),
        (b"Quiz in week 3", None, "txt"),
    ],
)
def test_the_kind_comes_from_the_bytes_when_the_name_is_wrong_or_missing(data, name, kind):
    assert read(data, name).kind == kind


@pytest.mark.parametrize(
    "name, kind",
    [
        ("outline.csv", "csv"),
        ("OUTLINE.CSV", "csv"),
        ("outline.md", "md"),
        ("outline.txt", "txt"),
        ("outline.htm", "html"),
        ("outline.html", "html"),
        ("outline.rtf", "txt"),  # any other text is sent as plain text
        (None, "txt"),
    ],
)
def test_plain_text_looks_the_same_inside_so_the_name_decides(name, kind):
    assert read(b"Task,Weight\nQuiz,10%\n", name).kind == kind


# ---------- Word ----------


def test_word_paragraphs_and_table_rows_come_out_in_order():
    data = docx_file(
        "33130 Mathematics 1",
        "Assessment tasks",
        rows=[["Task", "Weight", "Due"], ["Skills Test 1", "10%", "Week 2"], ["Final exam", "50%", "Exam period"]],
    )
    assert text_of(data) == (
        "33130 Mathematics 1\nAssessment tasks\nTask | Weight | Due\nSkills Test 1 | 10% | Week 2\n"
        "Final exam | 50% | Exam period"
    )


def test_word_text_in_content_controls_and_tracked_changes_is_read():
    # Content controls (w:sdt) and tracked insertions (w:ins) wrap text that python-docx's
    # own .text skips. Deleted text (w:delText) must not be read.
    data = docx_with_body(
        "<w:sdt><w:sdtContent><w:p><w:r><w:t>33130 Mathematics 1</w:t></w:r></w:p></w:sdtContent></w:sdt>"
        '<w:p><w:r><w:t xml:space="preserve">Quiz 1 is due in </w:t></w:r>'
        '<w:del w:id="1" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:delText>week 3</w:delText></w:r></w:del>'
        '<w:ins w:id="2" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:t>week 4</w:t></w:r></w:ins></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">Due: </w:t></w:r>'
        "<w:sdt><w:sdtContent><w:r><w:t>Friday</w:t></w:r></w:sdtContent></w:sdt></w:p>"
    )
    assert text_of(data) == "33130 Mathematics 1\nQuiz 1 is due in week 4\nDue: Friday"


def test_a_word_text_box_is_read_once_although_word_saves_it_twice():
    # Word saves a text box twice: once for new versions (mc:Choice) and once for old ones (mc:Fallback)
    box = "<w:txbxContent><w:p><w:r><w:t>Quiz 2 is in week 6</w:t></w:r></w:p></w:txbxContent>"
    data = docx_with_body(
        '<w:p><w:r><w:t xml:space="preserve">Before the box</w:t></w:r><w:r><mc:AlternateContent>'
        f'<mc:Choice Requires="wps"><w:drawing><wps:txbx>{box}</wps:txbx></w:drawing></mc:Choice>'
        f"<mc:Fallback><w:pict><v:shape><v:textbox>{box}</v:textbox></v:shape></w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
    )
    assert text_of(data) == "Before the box Quiz 2 is in week 6"


def test_a_table_inside_a_word_table_cell_stays_in_its_row():
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Quiz 1"
    inner = table.cell(0, 1).add_table(rows=1, cols=2)
    inner.cell(0, 0).text = "Week"
    inner.cell(0, 1).text = "3"
    assert text_of(saved(document)) == "Quiz 1 | Week | 3"


def test_empty_word_table_rows_are_left_out():
    assert text_of(docx_file("Tasks", rows=[["Quiz", "10%"], ["", ""]])) == "Tasks\nQuiz | 10%"


# ---------- PowerPoint ----------


def test_slides_have_headings_tables_speaker_notes_and_grouped_shapes():
    assert text_of(pptx_file()) == (
        "Slide 1\nAssessment summary\nQuiz 1 is held in week 3\nTask | Weight\nQuiz 1 | 10%\n"
        "Speaker notes: Remind students that the quiz is online\n"
        "Slide 2\nFinal exam in the exam period"
    )


def test_a_shape_that_powerpoint_saves_twice_is_read_once():
    # Shapes that use newer features (like equations) are saved twice: for new versions and as a fallback
    shape = (
        '<p:sp><p:nvSpPr><p:cNvPr id="9" name="Box"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr/>'
        "<p:txBody><a:bodyPr/><a:p><a:r><a:t>Quiz 3 is in week 9</a:t></a:r></a:p></p:txBody></p:sp>"
    )
    both = (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        f'<mc:Choice Requires="a14">{shape}</mc:Choice><mc:Fallback>{shape}</mc:Fallback></mc:AlternateContent>'
    )
    add_both = {"ppt/slides/slide2.xml": lambda xml: xml.replace(b"</p:spTree>", f"{both}</p:spTree>".encode())}
    assert text_of(zip_with(pptx_file(), add_both)).endswith("Slide 2\nFinal exam in the exam period\nQuiz 3 is in week 9")


# ---------- OpenDocument ----------


def test_odt_paragraphs_headings_lists_and_tables():
    body = (
        "<text:h>33130 Mathematics 1</text:h>"
        "<text:tracked-changes><text:changed-region><text:deletion><text:p>Old due date: week 2</text:p>"
        "</text:deletion></text:changed-region></text:tracked-changes>"
        "<text:p>Quiz<text:s/>1<text:tab/>is due in <text:span>week 3</text:span>"
        "<office:annotation><text:p>A comment, not part of the outline</text:p></office:annotation></text:p>"
        "<text:list><text:list-item><text:p>Bring a calculator</text:p></text:list-item></text:list>"
        "<table:table><table:table-row><table:table-cell><text:p>Task</text:p></table:table-cell>"
        "<table:table-cell><text:p>Weight</text:p></table:table-cell></table:table-row>"
        "<table:table-row><table:table-cell><text:p>Quiz 1</text:p></table:table-cell>"
        "<table:table-cell><text:p>10%</text:p></table:table-cell></table:table-row></table:table>"
    )
    assert text_of(odf_file("text", body)) == (
        "33130 Mathematics 1\nQuiz 1 is due in week 3\nBring a calculator\nTask | Weight\nQuiz 1 | 10%"
    )


def test_odp_slides_have_headings_and_speaker_notes_without_slide_numbers():
    notes = (
        "<presentation:notes>"
        "<draw:frame><draw:text-box><text:p>The quiz is online</text:p></draw:text-box></draw:frame>"
        "<draw:frame><draw:text-box><text:p><text:page-number>&lt;number&gt;</text:page-number></text:p>"
        "</draw:text-box></draw:frame></presentation:notes>"
    )
    body = (
        f'<draw:page draw:name="page1"><draw:frame><draw:text-box><text:p>Quiz 1 in week 3</text:p></draw:text-box>'
        f"</draw:frame>{notes}</draw:page>"
        '<draw:page draw:name="page2"><draw:frame><table:table><table:table-row>'
        "<table:table-cell><text:p>Final exam</text:p></table:table-cell>"
        "<table:table-cell><text:p>Exam period</text:p></table:table-cell></table:table-row></table:table>"
        "</draw:frame></draw:page>"
    )
    assert text_of(odf_file("presentation", body)) == (
        "Slide 1\nQuiz 1 in week 3\nSpeaker notes: The quiz is online\nSlide 2\nFinal exam | Exam period"
    )


def test_ods_sheets_show_values_never_formulas_and_repeats_are_written_out():
    body = (
        '<table:table table:name="Assessments">'
        "<table:table-row><table:table-cell><text:p>Task</text:p></table:table-cell>"
        "<table:table-cell><text:p>Weight</text:p></table:table-cell></table:table-row>"
        '<table:table-row table:number-rows-repeated="3"><table:table-cell><text:p>Quiz</text:p></table:table-cell>'
        '<table:table-cell table:number-columns-repeated="2"><text:p>5%</text:p></table:table-cell></table:table-row>'
        '<table:table-row><table:table-cell><text:p>Total</text:p></table:table-cell>'
        '<table:table-cell table:formula="of:=SUM([.B2:.B3])" office:value-type="percentage" office:value="0.2">'
        "<text:p>20%</text:p></table:table-cell></table:table-row>"
        # LibreOffice ends every sheet like this: empty rows repeated to the bottom of the sheet
        '<table:table-row table:number-rows-repeated="1048571"><table:table-cell table:number-columns-repeated="1024"/>'
        "</table:table-row></table:table>"
        '<table:table table:name="Notes"><table:table-row><table:table-cell><text:p>Check Canvas</text:p>'
        "</table:table-cell></table:table-row></table:table>"
    )
    assert text_of(odf_file("spreadsheet", body)) == (
        "Sheet: Assessments\nTask | Weight\nQuiz | 5% | 5%\nQuiz | 5% | 5%\nQuiz | 5% | 5%\nTotal | 20%\nSheet: Notes\n"
        "Check Canvas"
    )


# ---------- spreadsheets ----------


def test_excel_sheets_show_values_dates_and_percentages_never_formulas():
    text = text_of(xlsx_file())
    assert text == XLS_TEXT
    assert "B2+B3" not in text


def test_an_excel_file_with_a_wrong_saved_size_still_has_every_row_read():
    # Some programs save the used area of a sheet wrongly, as if it were only cell A1
    data = zip_with(xlsx_file(), {"xl/worksheets/sheet1.xml": lambda xml: xml.replace(b'ref="A1:D5"', b'ref="A1:A1"')})
    assert b'ref="A1:A1"' in zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml")
    assert text_of(data) == XLS_TEXT


def test_an_old_excel_file_shows_values_dates_and_percentages_never_formulas():
    assert text_of((FIXTURES / "assessments.xls").read_bytes(), "assessments.xls") == XLS_TEXT


def test_a_locked_old_excel_file_is_refused(monkeypatch):
    # xlrd says this for an .xls file saved with a password (checked by hand with one made by LibreOffice)
    def locked(**options):
        raise documents.xlrd.XLRDError("Workbook is encrypted")

    monkeypatch.setattr(documents.xlrd, "open_workbook", locked)
    assert str(refusal((FIXTURES / "assessments.xls").read_bytes())) == documents.LOCKED_MESSAGE


def test_a_csv_file_is_one_sheet():
    data = 'Task,Weight,Due\n"Quiz 1, online",10%,"Week 3\nFriday"\n\nFinal exam,50%,\n'.encode()
    assert text_of(data, "outline.csv") == (
        "Sheet: 1\nTask | Weight | Due\nQuiz 1, online | 10% | Week 3 Friday\nFinal exam | 50%"
    )


def test_spreadsheet_reading_stops_at_the_row_limit_and_says_so(monkeypatch):
    monkeypatch.setattr(documents, "MAX_ROWS", 3)
    workbook = openpyxl.Workbook()
    for number in range(1, 6):
        workbook.active.append([f"Quiz {number}"])
    assert text_of(saved(workbook)) == f"Sheet: Sheet\nQuiz 1\nQuiz 2\nQuiz 3\n{documents.ROWS_CUT_NOTE}"


def test_spreadsheet_reading_stops_at_the_cell_limit_and_says_so(monkeypatch):
    monkeypatch.setattr(documents, "MAX_CELLS", 5)
    rows = "".join(f"Quiz {number},10%\n" for number in range(1, 5))
    assert text_of(rows.encode(), "outline.csv") == f"Sheet: 1\nQuiz 1 | 10%\nQuiz 2 | 10%\n{documents.ROWS_CUT_NOTE}"


ODS_BOMB = odf_file(
    "spreadsheet",
    # A million rows of a million cells, saved in a few bytes with repeat counts
    '<table:table table:name="Bomb"><table:table-row table:number-rows-repeated="1000000">'
    '<table:table-cell table:number-columns-repeated="1000000"><text:p>x</text:p></table:table-cell>'
    "</table:table-row></table:table>",
)


def test_a_huge_repeat_count_in_an_ods_file_stops_at_the_limits(monkeypatch):
    monkeypatch.setattr(documents, "MAX_ROWS", 3)
    monkeypatch.setattr(documents, "MAX_CELLS", 4)
    assert text_of(ODS_BOMB) == f"Sheet: Bomb\nx | x | x | x\n{documents.ROWS_CUT_NOTE}"


def test_a_huge_repeat_count_in_an_ods_file_stays_small_with_the_real_limits():
    # One row of 50,000 cells is already about 200,000 characters, so the text limit cuts it
    text = text_of(ODS_BOMB)
    assert text.startswith("Sheet: Bomb\nx | x | x")
    assert text.endswith(documents.TEXT_CUT_NOTE)
    assert len(text) == documents.MAX_TEXT_CHARS + 1 + len(documents.TEXT_CUT_NOTE)


# ---------- text and web pages ----------


@pytest.mark.parametrize(
    "data, text",
    [
        (b"# Assessments\n\n- Quiz 1:  week 3\n", "# Assessments\n\n- Quiz 1:  week 3\n"),  # kept exactly
        (b"\xef\xbb\xbfQuiz 1", "Quiz 1"),  # UTF-8 with the mark Windows Notepad adds
        ("Quiz 1 – week 3".encode("utf-16"), "Quiz 1 – week 3"),  # UTF-16, with its first two bytes
        ("Quiz 1 – week 3".encode("cp1252"), "Quiz 1 � week 3"),  # an old Windows file, one character lost
    ],
)
def test_text_and_markdown_files_are_sent_as_they_are(data, text):
    assert text_of(data, "outline.md") == text


def test_a_web_page_keeps_its_words_and_table_rows_and_loses_scripts_and_styles():
    page = b"""<!DOCTYPE html><html><head><title>33130 Mathematics 1</title>
    <style>p { color: red; }</style><script>document.write("Fake: due tomorrow");</script></head>
    <body><h1>Assessments</h1><p>Quiz 1 &amp; Quiz 2 are
    online.<br>Bring a calculator.</p><!-- a comment -->
    <table><tr><th>Task</th><th>Weight</th></tr>
    <tr><td><p>Quiz 1</p><p>(online)</p></td><td>10&#37;</td></tr></table>
    <noscript>Turn on JavaScript</noscript><template><p>Hidden</p></template><p>The end</p></body></html>"""
    assert text_of(page, "outline.html") == (
        "33130 Mathematics 1\nAssessments\nQuiz 1 & Quiz 2 are online.\nBring a calculator.\n"
        "Task | Weight\nQuiz 1 (online) | 10%\nThe end"
    )


# ---------- macros ----------


@pytest.mark.parametrize("name", ["outline.docm", "outline.XLSM", "outline.pptm"])
def test_files_named_as_macro_files_are_always_refused(name):
    assert str(refusal(docx_file("Assignment 1"), name)) == documents.MACRO_MESSAGE


WORD_TYPE = documents.OFFICE_TYPES["docx"].encode()
MACRO_WORD_TYPE = b"application/vnd.ms-word.document.macroEnabled.main+xml"


@pytest.mark.parametrize(
    "changes",
    [
        # a .docm saved as .docx: its main part says it can hold macros
        {"[Content_Types].xml": lambda xml: xml.replace(WORD_TYPE, MACRO_WORD_TYPE)},
        # the macros themselves
        {"word/vbaProject.bin": b"macros"},
        # macros listed in the content types
        {"[Content_Types].xml": lambda xml: xml.replace(
            b"</Types>", b'<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')},
    ],
)
def test_office_files_with_macros_inside_are_refused_whatever_their_name(changes):
    data = zip_with(docx_file("Assignment 1"), changes)
    assert str(refusal(data, "outline.docx")) == documents.MACRO_MESSAGE


def test_excel_files_with_old_style_macro_sheets_are_refused():
    sheet_type = b"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
    data = zip_with(xlsx_file(), {"[Content_Types].xml": lambda xml: xml.replace(
        sheet_type, b"application/vnd.ms-excel.macrosheet+xml", 1)})
    assert str(refusal(data, "outline.xlsx")) == documents.MACRO_MESSAGE


@pytest.mark.parametrize("storage", ["Macros", "_VBA_PROJECT_CUR"])
def test_old_word_and_excel_files_with_macros_are_refused(storage):
    # Real files keep macros in a storage (a folder) with this name. A stream with the same name is enough here.
    data = ole_file({"WordDocument": word_97_header(), storage: b"macros"})
    assert str(refusal(data, "outline.doc")) == documents.MACRO_MESSAGE


# ---------- files locked with a password ----------


def locked_zip_part() -> bytes:
    """A Word file where one part is marked as locked with a zip password.

    Python's zipfile clears this flag when it writes a part, so the flag is
    set afterwards in the part's two headers: its own and the one in the
    zip's table of contents.
    """
    data = bytearray(docx_file("Assignment 1"))
    name = b"word/document.xml"
    for signature, flag_at, name_at in [(b"PK\x03\x04", 6, 30), (b"PK\x01\x02", 8, 46)]:
        position = data.find(signature)
        while data[position + name_at : position + name_at + len(name)] != name:
            position = data.find(signature, position + 1)
            assert position != -1
        data[position + flag_at] |= 1  # bit 1 of the flags means "locked with a password"
    return bytes(data)


@pytest.mark.parametrize(
    "data, name",
    [
        # Word, Excel and PowerPoint put a locked file inside an old style container
        (ole_file({"EncryptionInfo": b"info", "EncryptedPackage": b"secret"}), "outline.docx"),
        (ole_file({"EncryptionInfo": b"info", "EncryptedPackage": b"secret"}), None),
        (odf_file("text", "<text:p>Assignment 1</text:p>", locked=True), "outline.odt"),
        (ole_file({"WordDocument": word_97_header(locked=True)}), "outline.doc"),
        (locked_zip_part(), "outline.docx"),
    ],
)
def test_files_locked_with_a_password_are_refused_with_the_list_of_formats(data, name):
    error = refusal(data, name)
    assert str(error) == documents.LOCKED_MESSAGE
    assert str(error).startswith("This file is locked with a password")
    assert documents.FORMAT_LIST in str(error)


# ---------- size limits and zip bombs ----------


def test_a_file_over_10_mb_is_refused_and_one_of_exactly_10_mb_is_not():
    assert str(refusal(b"%PDF-" + b"0" * documents.MAX_FILE_BYTES)) == documents.TOO_BIG_MESSAGE
    assert read(b"%PDF-" + b"0" * (documents.MAX_FILE_BYTES - 5)).kind == "pdf"


def test_a_zip_that_would_unpack_to_more_than_50_mb_is_refused():
    # 51 MB of zeros packs into about 50 KB, the classic zip bomb trick
    data = zip_with(docx_file("Assignment 1"), {"word/media/padding.bin": b"\0" * (51 * 1024 * 1024)})
    assert len(data) < 200_000
    assert str(refusal(data)) == documents.ZIP_BOMB_MESSAGE


def test_a_zip_with_too_many_parts_is_refused():
    parts = {f"part{number}.xml": "<a/>" for number in range(documents.MAX_ZIP_PARTS + 1)}
    assert str(refusal(zip_file(parts))) == documents.ZIP_BOMB_MESSAGE


def test_python_never_unpacks_more_than_a_zip_part_declares():
    # The zip bomb limit adds up the sizes each part declares. This shows that a part
    # which lies about its size cannot unpack more than it declares.
    data = bytearray(zip_file({"content.xml": b"x" * 100_000}))
    central = data.find(b"PK\x01\x02")  # the part's entry in the zip's table of contents
    data[central + 24 : central + 28] = struct.pack("<I", 100)  # claim it unpacks to only 100 bytes
    archive = zipfile.ZipFile(io.BytesIO(bytes(data)))
    assert archive.getinfo("content.xml").file_size == 100
    with pytest.raises(zipfile.BadZipFile, match="Bad CRC-32"):
        archive.read("content.xml")  # stops after 100 bytes, which do not match the saved checksum


def test_xml_tricks_like_the_billion_laughs_are_refused():
    laughs = '<!DOCTYPE l [<!ENTITY a "haha"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
    data = zip_with(
        odf_file("text", "<text:p>Assignment 1</text:p>"),
        {"content.xml": lambda xml: xml.replace(b"<office:document-content", f"{laughs}<office:document-content".encode())
         .replace(b"Assignment 1", b"&b;")},
    )
    error = refusal(data)
    assert str(error) == documents.DAMAGED_MESSAGE
    assert type(error.__cause__).__name__ == "EntitiesForbidden"  # defusedxml stopped it


def test_long_text_is_cut_and_the_cut_is_marked():
    text = text_of(b"x" * (documents.MAX_TEXT_CHARS + 50), "outline.txt")
    assert text == "x" * documents.MAX_TEXT_CHARS + "\n" + documents.TEXT_CUT_NOTE


# ---------- empty, unknown and damaged files ----------


def test_an_empty_file_is_refused_with_the_list_of_formats():
    error = refusal(b"", "outline.pdf")
    assert str(error) == documents.EMPTY_MESSAGE
    assert documents.FORMAT_LIST in str(error)


@pytest.mark.parametrize(
    "data",
    [
        docx_file(),  # a Word file with no paragraphs at all
        b" \n\t ",
        odf_file("text", "<text:p/>"),
    ],
)
def test_a_file_with_no_text_is_refused(data):
    assert str(refusal(data, "outline.txt")) == documents.NO_TEXT_MESSAGE


@pytest.mark.parametrize(
    "data",
    [
        picture("GIF"),
        picture("BMP"),
        bytes(range(256)) * 4,  # some other binary file
        zip_file({"notes.txt": "Quiz in week 3"}),  # a zip, but not an Office or OpenDocument file
        zip_file({"mimetype": "application/epub+zip", "META-INF/container.xml": "<a/>"}),  # an e-book
        zip_with(docx_file("Assignment 1"), {"[Content_Types].xml": lambda xml: xml.replace(
            b"document.main+xml", b"template.main+xml")}),  # a Word template (.dotx)
        ole_file({"Contents": b"something else"}),  # an old style container that is not .doc, .xls or .ppt
    ],
)
def test_kinds_groot_cannot_read_are_refused_with_the_list_of_formats(data):
    error = refusal(data, "outline.pdf")
    assert str(error) == documents.UNKNOWN_MESSAGE
    assert documents.FORMAT_LIST in str(error)


@pytest.mark.parametrize(
    "data",
    [
        b"PK\x03\x04 the start of a zip and nothing else",
        docx_file("Assignment 1")[:3000],  # cut off half way
        zip_with(docx_file("Assignment 1"), {"word/document.xml": b"<w:document"}),  # broken XML
        documents.OLE_START + b"rubbish" * 100,
        b"%PDF-1.7\n/Encrypt but nothing else",
    ],
)
def test_a_damaged_file_gets_a_clear_message_and_keeps_the_real_error(data):
    error = refusal(data)
    assert str(error) == documents.DAMAGED_MESSAGE
    assert error.__cause__ is not None  # the library's own error stays attached for debugging


def test_a_file_name_that_is_not_text_is_a_programming_mistake_not_a_damaged_file():
    # For example extract_items(pdf, client) from before the filename argument existed
    with pytest.raises(TypeError):
        read(b"%PDF-1.7", object())


# ---------- old Word and PowerPoint files (.doc, .ppt) ----------


class FakeLibreOffice:
    """Stands in for subprocess.run. Each run writes `output` as the converted file, unless it is None."""

    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def run(self, command, **options):
        source = Path(command[-1])
        settings = source.parent / "profile" / "user" / "registrymodifications.xcu"
        self.calls.append(
            {"command": command, "options": options, "source": source.read_bytes(),
             "settings": settings.read_text(encoding="utf-8")}
        )
        if self.error is not None:
            raise self.error
        if self.output is not None:
            folder = Path(command[command.index("--outdir") + 1])
            new = command[command.index("--convert-to") + 1]
            (folder / f"{source.stem}.{new}").write_bytes(self.output)
        return subprocess.CompletedProcess(command, 0, b"", b"")  # LibreOffice says 0 even when it fails


@pytest.fixture
def libreoffice(monkeypatch):
    """LibreOffice installed as "soffice", with subprocess.run replaced by a FakeLibreOffice."""
    fake = FakeLibreOffice()
    monkeypatch.setattr(documents.shutil, "which", lambda name: "/opt/libreoffice/soffice" if name == "soffice" else None)
    monkeypatch.setattr(documents.subprocess, "run", fake.run)
    return fake


@pytest.mark.parametrize("data, name", [(DOC, "outline.doc"), (PPT, "outline.ppt"), (DOC, None), (PPT, "outline.pdf")])
def test_old_files_without_libreoffice_get_the_save_as_message(monkeypatch, data, name):
    monkeypatch.setattr(documents.shutil, "which", lambda program: None)
    error = refusal(data, name)
    assert str(error) == "This is an old Word/PowerPoint file. Save it as .docx, .pptx or PDF and try again."


def test_an_old_word_file_is_converted_by_libreoffice_and_then_read(libreoffice):
    libreoffice.output = docx_file("Assignment 1", rows=[["Quiz", "10%"]])

    document = read(DOC, "my outline.doc")

    assert (document.kind, document.text) == ("doc", "Assignment 1\nQuiz | 10%")
    [call] = libreoffice.calls
    command = call["command"]
    source = Path(command[-1])
    assert command[0] == "/opt/libreoffice/soffice"
    assert command[1] == f"-env:UserInstallation={(source.parent / 'profile').as_uri()}"  # a new profile
    assert call["settings"] == documents.NO_MACROS_SETTINGS  # in which every macro is switched off
    assert '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>' in call["settings"]
    assert command[2:6] == ["--headless", "--norestore", "--convert-to", "docx"]
    assert source.name == "outline.doc"  # a fixed name, never the student's file name
    assert call["source"] == DOC
    assert call["options"] == {"capture_output": True, "timeout": documents.CONVERT_TIMEOUT_SECONDS}
    assert not Path(command[-1]).parent.exists()  # the temporary folder is cleaned up


def test_an_old_powerpoint_file_is_converted_by_libreoffice_and_then_read(libreoffice):
    libreoffice.output = pptx_file()
    document = read(PPT, "lecture.ppt")
    assert document.kind == "ppt"
    assert document.text.startswith("Slide 1\nAssessment summary\n")
    assert libreoffice.calls[0]["command"][5] == "pptx"


def test_libreoffice_is_also_found_by_its_other_name(libreoffice, monkeypatch):
    monkeypatch.setattr(documents.shutil, "which", lambda name: "/usr/bin/libreoffice" if name == "libreoffice" else None)
    libreoffice.output = docx_file("Assignment 1")
    assert text_of(DOC) == "Assignment 1"
    assert libreoffice.calls[0]["command"][0] == "/usr/bin/libreoffice"


@pytest.mark.parametrize(
    "output, error, message",
    [
        (None, None, documents.CONVERT_FAILED_MESSAGE),  # LibreOffice made no file
        (b"not a Word file", None, documents.CONVERT_FAILED_MESSAGE),  # it made something else
        (None, subprocess.TimeoutExpired("soffice", 60), documents.CONVERT_TIMEOUT_MESSAGE),
        (None, PermissionError("not allowed to run it"), documents.CONVERT_FAILED_MESSAGE),
    ],
)
def test_a_failed_conversion_is_a_clear_error(libreoffice, output, error, message):
    libreoffice.output, libreoffice.error = output, error
    assert str(refusal(DOC, "outline.doc")) == message


def test_the_converted_file_gets_the_same_checks_as_an_upload(libreoffice):
    libreoffice.output = zip_with(docx_file("Assignment 1"), {"word/vbaProject.bin": b"macros"})
    assert str(refusal(DOC, "outline.doc")) == documents.MACRO_MESSAGE
