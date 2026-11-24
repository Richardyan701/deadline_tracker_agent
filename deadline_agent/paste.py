"""Add many deadlines at once from a pasted list, one deadline per line.

Each line is a title and when it is due, and the subject if the student
likes, for example:

    Quiz 1, friday week 3 5pm, Statistics
    Essay | 20 dec | Academic Writing
    Lab report due wednesday 9am for Biology

Columns copied from a spreadsheet (which arrive separated by tabs) work too,
and bullets or numbers at the start of a line are ignored. No AI is used:
each date goes through the same rules as adding one deadline (tools.py).

check() shows how every line was understood, and nothing is saved until
add() is called with the same text. Only the Python standard library is
used, so this also runs on Groot's website (web/browser.py).
"""

import re

from . import tools

MAX_LINES = 100  # a whole semester fits easily
MAX_LINE_LENGTH = 300

# What can separate the title, the date and the subject, in the order they are tried.
# A comma comes before the dashes, so a title like "Lab 2 - Circuits, friday 5pm" keeps its dash.
SEPARATORS = ["\t", "|", ";", ",", " — ", " – ", " - "]

# A bullet or a number at the start of a line, like "- ", "• ", "3. " or "3) "
BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+")

# A line with no separator: "Essay due 20 dec" or "Lab report by friday 9am for Biology"
DUE_WORDS = re.compile(r"(?P<title>.+?)\s+(?:due|by)\s+(?P<when>.+?)(?:\s+for\s+(?P<subject>.+))?", re.IGNORECASE)

NO_SPLIT = (
    "Groot couldn't tell where the title ends. Put a comma between the title and the date, like 'Quiz 1, friday 5pm'."
)


def _lines(text: str) -> list[str]:
    """The pasted lines with their bullets taken off, leaving out empty ones."""
    lines = (BULLET.sub("", line).strip() for line in text.splitlines())
    return [line for line in lines if line]


def _works(when: str, now) -> bool:
    try:
        tools._understand_due_date(when, now)
    except ValueError:
        return False
    return True


def _split(line: str, now) -> tuple[str, str, str] | None:
    """The title, the date words and the subject in one line, or None if Groot cannot tell them apart.

    A date can contain the separator too, like "20 nov, 5pm", so after the
    title Groot takes the longest run of parts that is a date that works,
    and what is left is the subject. If no run works, the first part is the
    date, so the row shows that date's problem.
    """
    for separator in SEPARATORS:
        if separator in line:
            title, *rest = [part.strip() for part in line.split(separator)]
            rest = [part for part in rest if part]
            if not title or not rest:
                return None
            for count in range(len(rest), 0, -1):
                when = " ".join(rest[:count])
                if _works(when, now):
                    return title, when, ", ".join(rest[count:])
            return title, rest[0], ", ".join(rest[1:])
    match = DUE_WORDS.fullmatch(line)
    if match:
        return match["title"].strip(), match["when"].strip(), (match["subject"] or "").strip()
    return None


def check(text) -> dict:
    """How each line of the pasted text would be added, without saving anything.

    Returns "status", a "message" and "rows". Each row has the line number,
    "title", "subject", "due" (the full date, or "" when it is not clear),
    "ok" (True when the line can be added) and a "message" for a line with a problem.
    """
    if not isinstance(text, str) or not text.strip():
        return {"status": "error", "message": "Paste your deadlines first, one per line.", "rows": []}
    lines = _lines(text)
    if len(lines) > MAX_LINES:
        return {"status": "error", "message": f"Paste up to {MAX_LINES} lines at a time.", "rows": []}

    now = tools._now()
    with tools._file_lock:
        saved_titles = {tools._title_key(deadline["title"]) for deadline in tools._load_deadlines()}
    seen = set()
    rows = []
    for number, line in enumerate(lines, 1):
        row = {"line": number, "text": line, "title": "", "subject": "", "due": "", "ok": False, "message": ""}
        rows.append(row)
        if len(line) > MAX_LINE_LENGTH:
            row["message"] = f"This line is longer than {MAX_LINE_LENGTH} characters."
            continue
        parts = _split(line, now)
        if parts is None:
            row["message"] = NO_SPLIT
            continue
        row["title"], when, row["subject"] = parts
        try:
            saved = tools._understand_due_date(when, now)
        except ValueError as error:
            row["message"] = str(error)
            continue
        row["due"] = tools._friendly(tools._parse_due_date(saved))
        key = tools._title_key(row["title"])
        if key in saved_titles:
            row["message"] = f"You already have a deadline called '{row['title']}'."
        elif key in seen:
            row["message"] = f"'{row['title']}' is in this list twice."
        else:
            seen.add(key)
            row["ok"] = True
            row["message"] = tools._week_note(when, saved).strip()  # week number, quiet week or holiday notes

    ready = sum(row["ok"] for row in rows)
    if ready == len(rows):
        message = f"All {tools._plural(ready, 'line')} look good. Check the dates, then add them."
    elif ready:
        message = f"{ready} of {len(rows)} lines are ready. Fix the others, or add the ready ones now."
    else:
        message = "None of these lines can be added yet. Each one says why."
    return {"status": "success" if ready else "error", "message": message, "rows": rows}


def add(text) -> dict:
    """Add every line of the pasted text that check() says is ready, and say what happened to each line.

    The text is checked again here, so nothing that has changed since the
    preview can slip through. Each ready line is saved with
    tools.add_deadline, which also refuses sensitive details.
    """
    checked = check(text)
    if not checked["rows"]:
        return checked
    added = 0
    for row in checked["rows"]:
        if not row["ok"]:
            continue
        result = tools.add_deadline(row["title"], _when_of(row["text"]), row["subject"])
        row["ok"] = result["status"] == "success"
        row["message"] = result["message"]
        added += row["ok"]
    total = len(checked["rows"])
    message = f"Added {tools._plural(added, 'deadline')}." if added == total else f"Added {added} of {total} lines."
    return {"status": "success" if added else "error", "message": message, "rows": checked["rows"]}


def _when_of(line: str) -> str:
    """The date words of a line again, worked out the same way check() did."""
    parts = _split(line, tools._now())
    return parts[1] if parts else ""
