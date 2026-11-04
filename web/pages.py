"""The HTML of Groot's two pages: the home page and the outline drop box.

Titles and subjects are typed by the student (or found in a PDF), so they
can contain anything, even "<script>". Every piece of text that comes from
a deadline goes through escape(), which turns < > & " ' into HTML codes.
The browser then shows that text as it is and never runs it as code.
"""

from datetime import datetime
from html import escape

from deadline_agent import tools

# Opens ADK's chat with Groot already chosen
CHAT_PATH = "/dev-ui/?app=deadline_agent"

# The groups get_reminders gives back, in the order they are shown
REMINDER_GROUPS = ["overdue", "due_today", "due_soon"]

ADD_FORM = """<form id="add-form">
<div class="field">
<label for="add-title">Title</label>
<input id="add-title" name="title" autocomplete="off">
</div>
<div class="field">
<label for="add-when">When is it due?</label>
<input id="add-when" name="due_date" autocomplete="off" aria-describedby="add-when-hint">
<p id="add-when-hint" class="hint">Plain words work, like "next friday 5pm", "in 3 days" or "20 nov".</p>
</div>
<div class="field">
<label for="add-subject">Subject <span class="optional">(optional)</span></label>
<input id="add-subject" name="subject" autocomplete="off">
</div>
<button type="submit">Add deadline</button>
<p id="add-message" class="message" role="status"></p>
</form>"""


def home_page(reminders: dict, deadlines: list[dict], now: datetime) -> str:
    """The home page.

    reminders is what tools.get_reminders() returns, deadlines is the list
    from tools.list_deadlines() (soonest first), and now is Sydney time.
    """
    body = f"""<header class="top">
<h1>Agent Groot</h1>
<p class="tagline">Your study deadlines, all in one place.</p>
<div class="actions">
<button type="button" id="export-button">Export to calendar</button>
<a class="button" href="/groot/import">Import from outlines</a>
<a class="button" href="{CHAT_PATH}">Chat with Groot</a>
</div>
<p id="top-message" class="message" role="status"></p>
</header>
<main>
<section aria-labelledby="due-soon-heading">
<h2 id="due-soon-heading">Due soon</h2>
{due_soon(reminders)}
</section>
<section aria-labelledby="all-heading">
<h2 id="all-heading">All deadlines</h2>
<p id="table-message" class="message" role="status" tabindex="-1"></p>
{deadline_table(deadlines, now)}
</section>
<section aria-labelledby="add-heading">
<h2 id="add-heading">Add a deadline</h2>
{ADD_FORM}
</section>
</main>"""
    return _layout("Agent Groot", "home.js", body)


def due_soon(reminders: dict) -> str:
    """The "Due soon" list: overdue, due today and due in the next 7 days.

    The groups and the "when" phrases (like "in 3 hours" or "2 days
    overdue") come from get_reminders, so they always match the chat.
    """
    items = "".join(_reminder(group, item) for group in REMINDER_GROUPS for item in reminders[group])
    listed = f'<ul class="reminders">{items}</ul>' if items else ""
    return f'<div id="due-soon-list"><p class="summary">{escape(reminders["message"])}</p>{listed}</div>'


def _reminder(group: str, item: dict) -> str:
    due = tools._friendly(tools._parse_due_date(item["due_date"]))
    subject = f' <span class="subject">{escape(item["subject"])}</span>' if item["subject"] else ""
    return (
        f'<li class="{group}"><span class="when">{escape(item["when"])}:</span> '
        f'<span class="title">{escape(item["title"])}</span>{subject} '
        f'<span class="due">Due {escape(due)}</span></li>'
    )


def deadline_table(deadlines: list[dict], now: datetime) -> str:
    """Every deadline, soonest first, with Mark done and Delete buttons. Finished ones are greyed."""
    if not deadlines:
        return (
            '<div id="deadline-table"><p class="empty">You have no deadlines saved yet. Add one below, '
            'or <a href="/groot/import">import them from your subject outlines</a>.</p></div>'
        )
    rows = "".join(_deadline_row(deadline, now) for deadline in deadlines)
    return (
        '<div id="deadline-table"><table>'
        '<caption class="visually-hidden">All your deadlines, soonest first</caption>'
        '<thead><tr><th scope="col">Deadline</th><th scope="col">Due</th>'
        '<th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _deadline_row(deadline: dict, now: datetime) -> str:
    due = tools._parse_due_date(deadline["due_date"])
    if deadline["done"]:
        state, status = "done", "Done"
    else:
        state = "overdue" if due < now else "upcoming"
        status = tools._time_phrase(due, now)  # the same phrases as the reminders
    subject = f'<span class="subject">{escape(deadline["subject"])}</span>' if deadline["subject"] else ""
    buttons = "" if deadline["done"] else _button("done", "Mark done", "secondary", deadline["title"])
    buttons += _button("delete", "Delete", "danger", deadline["title"])
    return (
        f'<tr class="{state}">'
        f'<td><span class="title">{escape(deadline["title"])}</span>{subject}</td>'
        f'<td><span class="due">{escape(tools._friendly(due))}</span> <span class="status">{escape(status)}</span></td>'
        f'<td><div class="row-actions">{buttons}</div></td></tr>'
    )


def _button(action: str, label: str, style: str, title: str) -> str:
    """A Mark done or Delete button for one deadline.

    escape() also turns quotes into codes, so the title is safe inside
    data-title="...", and the browser hands the JavaScript the exact title
    back. The hidden words tell a screen reader which deadline it is for.
    """
    title = escape(title)
    return (
        f'<button type="button" class="{style}" data-action="{action}" data-title="{title}">'
        f'{label}<span class="visually-hidden">: {title}</span></button>'
    )


def import_page(sessions: dict, default_session: str) -> str:
    """The outline drop box. sessions is uts_calendar.SESSIONS, so the picker always matches the calendar."""
    options = "".join(
        f'<option value="{escape(code)}"{" selected" if code == default_session else ""}>{escape(info["name"])}</option>'
        for code, info in sessions.items()
    )
    body = f"""<header class="top">
<p><a href="/groot">Back to your deadlines</a></p>
<h1>Import from outlines</h1>
<p class="tagline">Drop in your subject outlines, check the deadlines Groot finds, then save the ones you want.</p>
</header>
<main>
<section aria-labelledby="files-heading">
<h2 id="files-heading">1. Choose your files</h2>
<div id="drop-zone" class="drop-zone">
<p class="drop-title">Drag your subject outline PDFs here, or</p>
<input id="outline-input" class="visually-hidden" type="file" accept=".pdf,application/pdf" multiple>
<label for="outline-input" class="button">Choose outline PDFs</label>
<p class="hint">1 to 8 outlines, each up to 10 MB.</p>
</div>
<p id="file-message" class="message" role="status"></p>
<ul id="outline-list" class="file-list"></ul>
<div class="field">
<label for="timetable-input">Your UTS timetable <span class="optional">(optional PDF)</span></label>
<input id="timetable-input" type="file" accept=".pdf,application/pdf" aria-describedby="timetable-hint">
<button type="button" id="timetable-clear" class="secondary">Remove timetable</button>
<p id="timetable-hint" class="hint">Groot uses it to find the day and time of your tutorials.</p>
</div>
<div class="field">
<label for="canvas-input">Canvas calendar feed link <span class="optional">(optional)</span></label>
<input id="canvas-input" type="url" autocomplete="off" spellcheck="false" aria-describedby="canvas-hint">
<p id="canvas-hint" class="hint">In Canvas, open Calendar, then Calendar Feed, and copy the link. Groot reads it once and never saves it. Keep it private, because anyone with the link can see your calendar.</p>
</div>
<div class="field">
<label for="session-select">Session</label>
<select id="session-select">{options}</select>
</div>
</section>
<section aria-labelledby="preview-heading">
<h2 id="preview-heading">2. Preview</h2>
<p class="warning">Preview sends each outline to Gemini, and each outline uses one Gemini request. Gemini's free tier allows 20 requests a day, so check your files first. The timetable and the Canvas link do not use Gemini.</p>
<p id="request-count">Choose at least one outline to preview.</p>
<button type="button" id="preview-button" disabled>Preview deadlines</button>
<p id="preview-message" class="message" role="status"></p>
<ul id="outline-results" class="results"></ul>
<ul id="notes" class="notes"></ul>
</section>
<section id="review" aria-labelledby="review-heading" hidden>
<h2 id="review-heading">3. Check and save</h2>
<p>Ticked rows are saved. A row that needs your date can be saved once you type one, like "25 aug 9am". Typed dates get the same checks as adding a deadline by hand.</p>
<p class="hint scroll-hint">Swipe the table sideways to see every column.</p>
<div class="table-wrap" role="region" aria-labelledby="review-heading" tabindex="0">
<table>
<caption class="visually-hidden">Deadlines found in your outlines</caption>
<thead><tr><th scope="col">Save</th><th scope="col">Deadline</th><th scope="col">Due</th><th scope="col">Status</th><th scope="col">Note</th></tr></thead>
<tbody id="review-body"></tbody>
</table>
</div>
<button type="button" id="save-button">Save ticked deadlines</button>
<p id="save-message" class="message" role="status"></p>
</section>
</main>"""
    return _layout("Import from outlines", "import.js", body)


def _layout(title: str, script: str, body: str) -> str:
    """The parts every page shares. script is the page's own JavaScript file in static/."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="/groot/static/groot.css">
<script type="module" src="/groot/static/{script}"></script>
</head>
<body>
{body}
</body>
</html>
"""
