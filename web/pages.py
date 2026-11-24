"""The HTML of Groot's two pages: the home page and the outline drop box.

Titles and subjects are typed by the student (or found in an outline), so
they can contain anything, even "<script>". Every piece of text that comes
from a deadline goes through escape(), which turns < > & " ' into HTML codes.
The browser then shows that text as it is and never runs it as code.
"""

from datetime import datetime
from html import escape

from deadline_agent import calendars, model_choice, region, tools

# Opens ADK's chat with Groot already chosen
CHAT_PATH = "/dev-ui/?app=deadline_agent"

# The groups get_reminders gives back, in the order they are shown
REMINDER_GROUPS = ["overdue", "due_today", "due_soon"]

# UTS's own page about short extensions. The tip links to it, so students can check the latest rules there.
UTS_EXTENSIONS_URL = (
    "https://www.uts.edu.au/current-students/managing-your-course/classes-and-assessment/special-circumstances/short-extensions"
)


def uts_tip() -> str:
    """A short tip about UTS's 3-day short extensions, for the space under the due date box.

    It is shown only while a UTS session is chosen. Checked against UTS's
    page on 24 Nov 2026: 72 hours for most Canvas assignments, granted
    instantly with no documents, requested in Canvas (Assignment Extensions)
    in the 14 days before the due time, and not for quizzes, exams or
    in-class tasks. Groot never moves a date by itself, because nothing
    changes until the student asks UTS for the extension.
    It always has the id uts-tip, so home.js can swap in a fresh copy after
    the session changes.
    """
    session = tools._chosen_session()
    if session is None or calendars.session_info(session)["university"] != "uts":
        return '<p id="uts-tip" class="tip" hidden></p>'
    return (
        '<p id="uts-tip" class="tip"><strong>UTS tip:</strong> most Canvas assignments can get an instant '
        "3-day extension, no documents needed. Request it in Canvas (Assignment Extensions) in the 14 days "
        "before it's due. Not for quizzes, exams or in-class tasks. "
        f'<a href="{UTS_EXTENSIONS_URL}" target="_blank" rel="noopener noreferrer">UTS rules</a></p>'
    )


def add_form() -> str:
    """The form for adding a deadline, with the UTS tip under the due date box when it applies."""
    return f"""<form id="add-form">
<div class="field">
<label for="add-title">Title</label>
<input id="add-title" name="title" autocomplete="off">
</div>
<div class="field">
<label for="add-when">When is it due?</label>
<input id="add-when" name="due_date" autocomplete="off" aria-describedby="add-when-hint uts-tip">
<p id="add-when-hint" class="hint">Plain words work, like "next friday 5pm", "in 3 days", "20 nov" or "friday week 7".</p>
{uts_tip()}
</div>
<div class="field">
<label for="add-subject">Subject <span class="optional">(optional)</span></label>
<input id="add-subject" name="subject" autocomplete="off">
</div>
<button type="submit">Add deadline</button>
<p id="add-message" class="message" role="status"></p>
</form>"""


# "Add many at once": paste a list, check how Groot reads each line, then add them (see paste.py)
PASTE_BOX = """<details id="paste-box" class="paste-box">
<summary>Add many at once</summary>
<form id="paste-form">
<label for="paste-text">One deadline per line: the title, when it's due, and the subject if you like.</label>
<textarea id="paste-text" name="text" rows="6" spellcheck="false" aria-describedby="paste-hint"></textarea>
<p id="paste-hint" class="hint">For example:<br>Quiz 1, friday week 3 5pm, Statistics<br>Essay, 20 dec, Academic Writing<br>Lab report due wednesday 9am</p>
<div class="actions">
<button type="submit" class="secondary">Check the list</button>
<button type="button" id="paste-add" hidden>Add these</button>
</div>
<p id="paste-message" class="message" role="status"></p>
<ol id="paste-rows" class="paste-rows"></ol>
</form>
</details>"""


# The Edit box. It sits outside the lists, so it stays when they are drawn again.
# home.js fills it in from the Edit button that was clicked.
EDIT_DIALOG = """<dialog id="edit-dialog" aria-labelledby="edit-heading">
<form id="edit-form" method="dialog">
<h2 id="edit-heading">Edit deadline</h2>
<div class="field">
<label for="edit-title">Title</label>
<input id="edit-title" name="new_title" autocomplete="off">
</div>
<div class="field">
<label for="edit-when">When is it due?</label>
<input id="edit-when" name="due_date" autocomplete="off" aria-describedby="edit-when-hint">
<p id="edit-when-hint" class="hint">Leave it as it is to keep the date, or type plain words like "next friday 5pm".</p>
</div>
<div class="field">
<label for="edit-subject">Subject <span class="optional">(optional)</span></label>
<input id="edit-subject" name="subject" autocomplete="off">
</div>
<div class="row-actions">
<button type="submit">Save changes</button>
<button type="button" class="secondary" id="edit-cancel">Cancel</button>
</div>
<p id="edit-message" class="message" role="status"></p>
</form>
</dialog>"""


# ---------- what the pages say about the AI ----------
#
# Groot can use Gemini or a model from another company (model_choice.py), so
# the pages name the one in use and say where the student's words really go.

HELD_BACK = "card numbers, tax file numbers, passwords and similar details"


def _on_this_computer(model: str) -> bool:
    """True if the model runs on the student's own computer (Ollama), so nothing is sent to any company."""
    return model_choice.provider_of(model)["key"] is None


def home_privacy_note() -> str:
    """The privacy line on the home page, for the model in use."""
    model = model_choice.chosen_model()
    ai = model_choice.provider_of(model)["name"]
    if _on_this_computer(model):
        return (
            f"Your deadlines stay on this computer. Chat messages and previewed outlines are read by a model running "
            f"on this computer ({ai}), so they do not leave it either. Groot still holds back {HELD_BACK} when it spots them."
        )
    if model_choice.uses_gemini(model):
        where = "go to Google's Gemini, which may use and review them on the free tier"
    else:
        where = f"go to {ai}, which may use and review them, depending on its terms"
    return (
        f"Your deadlines stay on this computer. Chat messages and previewed outlines {where}, so never send sensitive "
        f"details such as your student ID. Groot holds back {HELD_BACK} when it spots them, but it cannot spot everything."
    )


def privacy_summary(website: bool = False) -> str:
    """The one short privacy line people actually read. The full note sits under "Privacy details"."""
    if website:
        return "Private: your deadlines are saved only in this browser."
    model = model_choice.chosen_model()
    if _on_this_computer(model):
        return "Private: your deadlines and chats stay on this computer."
    ai = model_choice.provider_of(model)["name"]
    return f"Your deadlines stay on this computer. The chat and outline import use {ai}, so never type private details."


def import_warnings() -> list[str]:
    """The warnings above the Preview button, for the model in use."""
    model = model_choice.chosen_model()
    ai = model_choice.provider_of(model)["name"]
    uses = f"Preview sends each outline to {ai}, and each outline uses one {ai} request."
    if model == model_choice.DEFAULT_MODEL:
        uses += " Gemini's free tier allows 20 requests a day, so check your files first."
    else:
        uses += " Check your files first."
    uses += f" The timetable and the Canvas link do not use {ai}."

    do_not = "Do not upload anything with sensitive personal details, such as your student ID."
    if _on_this_computer(model):
        privacy_note = (
            f"Privacy: outlines you preview are read by a model running on this computer ({ai}), so they do not leave it. "
            f"Groot still takes out {HELD_BACK} it spots."
        )
    else:
        if model_choice.uses_gemini(model):
            where = "are sent to Google's Gemini, and on the free tier Google may use and review them"
        else:
            where = f"are sent to {ai}, which may use and review them, depending on its terms"
        privacy_note = (
            f"Privacy: outlines you preview {where}. {do_not} Groot takes out {HELD_BACK} it spots before sending, "
            "but it cannot spot everything, and it cannot check a photo or a scanned page."
        )
    warnings = [uses, privacy_note]
    if not model_choice.uses_gemini(model):
        warnings.append(f"Groot can only send {ai} text, so a photo or a scanned PDF cannot be read while it is in use.")
    return warnings


def time_zone_notice() -> str:
    """A notice for a student whose Groot is set to a country other than Australia, or "".

    It says once, clearly, that Groot's clock has changed. home.js shows it
    until the student clicks OK, and shows it again if the time zone changes.
    """
    if tools.PLACE["time_zone"] == "Australia/Sydney":
        return ""
    zone = escape(tools.PLACE["time_zone"])
    return (
        f'<div id="time-zone-notice" class="warning time-zone-notice" role="status" data-zone="{zone}" hidden>'
        f'<p>Your time zone is now <strong>{escape(tools.PLACE["clock"])}</strong>. Every due date, reminder '
        "and calendar export uses it.</p>"
        '<button type="button" id="time-zone-ok" class="secondary">OK</button></div>'
    )


# The honest note under the Grades heading
GRADES_NOTE = (
    "The average you need on what's left of each subject for a Pass (50), Credit (65), Distinction (75) or "
    "High Distinction (85). Groot can't check minimum rules, like a minimum exam mark, so read your outline too."
)

BAND_KEYS = ["pass", "credit", "distinction", "high distinction"]


def home_page(reminders: dict, deadlines: list[dict], now: datetime, grades: list[dict] | None = None) -> str:
    """The home page.

    reminders is what tools.get_reminders() returns, deadlines is the list
    from tools.list_deadlines() (soonest first), now is local time and
    grades is tools._all_grade_reports() (one report per subject).
    """
    return _layout("Agent Groot", "home.js", home_body(reminders, deadlines, now, grades))


# What Groot's website says about where the deadlines are kept (see browser.py)
WEBSITE_NOTE = (
    "Your deadlines are saved only in this browser, on this device. Nothing is sent anywhere, "
    "so no one else can see them, but clearing this browser's data erases them, so download a backup now and then."
)

# The website's own section: backups and example deadlines. site/app.js gives the buttons their actions.
WEBSITE_SECTION = """<section aria-labelledby="browser-heading">
<h2 id="browser-heading">Your data in this browser</h2>
<p class="hint">Keep a backup in case this browser's data is cleared. It also moves your deadlines to another device.</p>
<div class="actions">
<button type="button" id="backup-button" class="secondary">Download backup</button>
<input id="restore-input" class="visually-hidden" type="file" accept=".json,application/json">
<label for="restore-input" class="button secondary">Restore a backup</label>
</div>
<h3>Just trying Groot?</h3>
<p class="hint">"Try a sample semester" fills your next semester with made-up assignments, like an essay due "sunday week 9 11:59pm", so you can see how everything works. Choose your university under "Add a deadline" first.</p>
<div class="actions">
<button type="button" id="sample-button" class="secondary">Try a sample semester</button>
<button type="button" id="remove-examples-button" class="secondary">Remove examples</button>
</div>
<p id="browser-message" class="message" role="status"></p>
</section>"""


def home_body(
    reminders: dict, deadlines: list[dict], now: datetime, grades: list[dict] | None = None, website: bool = False
) -> str:
    """The inside of the home page, which home_page wraps in the shared <head>.

    With website=True it is the version on Groot's website (browser.py), where
    everything runs in the student's own browser: no outline import or chat
    yet, a note that the deadlines stay in this browser, and backup buttons.
    """
    if website:
        actions = '<button type="button" id="export-button">Export to calendar</button>'
        note = WEBSITE_NOTE
    else:
        actions = (
            '<button type="button" id="export-button">Export to calendar</button>\n'
            '<a class="button" href="/groot/import">Import from outlines</a>\n'
            f'<a class="button" href="{CHAT_PATH}">Chat with Groot</a>'
        )
        note = home_privacy_note()
    return f"""<header class="top">
<h1>Agent Groot</h1>
<p class="tagline">Your study deadlines, all in one place.</p>
{week_line(now)}
<div class="actions">
{actions}
</div>
{export_nudge()}
{reminder_picker()}
<div class="privacy-note">
<p>{escape(privacy_summary(website), quote=False)}</p>
<details class="more"><summary>Privacy details</summary>
<p>{escape(note, quote=False)} Every date and time here is {escape(tools.PLACE["clock"])}.</p>
</details>
</div>
{time_zone_notice()}
<p id="top-message" class="message" role="status"></p>
</header>
<main>
{heads_up(reminders.get("clashes", []))}
<section aria-labelledby="due-soon-heading">
<h2 id="due-soon-heading">Due soon</h2>
{due_soon(reminders)}
</section>
<section aria-labelledby="all-heading">
<h2 id="all-heading">All deadlines</h2>
<p id="table-message" class="message" role="status" tabindex="-1"></p>
{deadline_table(deadlines, now, website)}
{EDIT_DIALOG}
</section>
<section aria-labelledby="add-heading">
<h2 id="add-heading">Add a deadline</h2>
{session_chooser(now)}
{add_form()}
{PASTE_BOX}
</section>
<section aria-labelledby="grades-heading">
<h2 id="grades-heading">Grades</h2>
<p class="hint">{escape(GRADES_NOTE if tools._grade_bands_apply() else tools.GRADES_OFF)}</p>
<p id="mark-message" class="message" role="status"></p>
{grades_section(deadlines, grades or [])}
</section>
{WEBSITE_SECTION if website else ""}
</main>"""


def export_nudge() -> str:
    """A line under the buttons when the calendar app's copy of the deadlines is missing or out of date.

    The calendar app only knows what was in the file at the last export, so
    a deadline added or moved later gets no reminder until the next export.
    It always has the id export-nudge, so home.js can swap in a fresh copy.
    """
    state = tools.calendar_state()
    if state == "never":
        text = "Export to calendar so your calendar app can remind you before each deadline."
    elif state == "changed":
        text = "Your deadlines or reminder times changed since your last export. Export again so your calendar has them all."
    else:
        return '<p id="export-nudge" class="nudge" hidden></p>'
    return f'<p id="export-nudge" class="nudge">{escape(text)}</p>'


def reminder_summary(keys) -> str:
    """The line on the closed reminder picker, like "Calendar reminders: 1 day and 5 hours before"."""
    return f"Calendar reminders: {tools.reminder_words(keys)} before" if keys else "Calendar reminders: off"


def reminder_picker() -> str:
    """The reminder times for the calendar file, ticked as chosen. home.js saves a change straight away.

    Web pages cannot pop up a reminder while they are closed, so the
    reminders go into the calendar file and the student's calendar app
    shows them (see tools.REMINDER_TIMES).
    """
    chosen = tools.chosen_reminders()
    boxes = "".join(
        f'<label class="check"><input type="checkbox" name="reminder" value="{key}"{" checked" if key in chosen else ""}>'
        f"{escape(words)}</label>"
        for key, (_, words) in tools.REMINDER_TIMES.items()
    )
    return (
        '<details id="reminder-picker" class="reminders">'
        f'<summary id="reminder-summary">{escape(reminder_summary(chosen))}</summary>'
        f'<fieldset><legend>Remind me this long before each deadline:</legend><div class="checks">{boxes}</div></fieldset>'
        '<p class="hint">Your calendar app shows these reminders, even when Groot is closed. '
        "After changing them, export to calendar again.</p>"
        '<p id="reminder-message" class="message" role="status"></p>'
        "</details>"
    )


def week_line(now: datetime) -> str:
    """The line under the tagline saying which week of the chosen session it is.

    It always has the id week-line, so home.js can swap in a fresh copy after
    the session changes.
    """
    session = tools._chosen_session()
    if session is None:
        text = 'Choose your university and session under "Add a deadline" to use week numbers, like "friday week 7".'
        return f'<p id="week-line" class="week-line">{escape(text)}</p>'
    info = calendars.session_info(session)
    name = f"{calendars.university_name(session)} {info['name']}"
    where = calendars.where_is(session, now.date())
    if where.startswith("week"):
        week, _, called = where.partition(", ")  # "week 8" and "SMU's recess week"
        text = f"Today is in {week} of {name}." + (f" It's {called}." if called else "")
    elif where == "a break with no week number":
        text = f"This week is a break with no week number in {name}."
    elif where == "the exam period":
        text = f"It is the exam period of {name}."
    elif where == "before week 1":
        first = calendars.week_start(session, 1)
        text = f"{name} has not started yet. Week 1 starts on {first.strftime('%A')} {first.day} {first.strftime('%b %Y')}."
    else:
        text = f"{name} has finished. Choose your next session to keep using week numbers."
    return f'<p id="week-line" class="week-line">{escape(text)}</p>'


def session_chooser(now: datetime) -> str:
    """The picker for the session that week numbers count in, with the chosen one selected.

    home.js saves a new choice through /groot/api/session. Only sessions that
    have not finished are offered.
    """
    chosen = tools._chosen_session()
    options = _session_picker(calendars.open_sessions(now.date()), custom=False, selected=chosen)
    return (
        '<div class="field">'
        '<label for="home-session">Week numbers count in <span class="optional">(optional)</span></label>'
        f'<select id="home-session" aria-describedby="home-session-hint">{options}</select>'
        '<p id="home-session-hint" class="hint">Then you can type dates like "friday week 7 5pm".</p>'
        '<p id="session-message" class="message" role="status"></p>'
        "</div>"
    )


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


def heads_up(clashes: list[dict]) -> str:
    """The "Heads up" box: deadlines that bunch up, from get_reminders' "clashes".

    It is always on the page so home.js can swap in a fresh copy, but it is
    hidden while there are no clashes.
    """
    hidden = "" if clashes else " hidden"
    items = "".join(f"<li>{escape(clash['message'])}</li>" for clash in clashes)
    return (
        f'<section id="heads-up" class="heads-up" aria-labelledby="heads-up-heading"{hidden}>'
        '<h2 id="heads-up-heading">Heads up</h2>'
        f'<ul class="clashes">{items}</ul></section>'
    )


def grades_section(deadlines: list[dict], grades: list[dict]) -> str:
    """The form to enter a mark or weight, then a summary for each subject.

    Outside Australia the Australian grade bands do not apply, so the section
    is left empty (the note above it says why). It is still drawn, because
    home.js swaps in a fresh copy after each change.
    """
    if not tools._grade_bands_apply():
        return '<div id="grades"></div>'
    if not deadlines:
        return '<div id="grades"><p class="empty">Add some deadlines first, then enter your marks here.</p></div>'
    options = "".join(
        f'<option value="{escape(d["title"])}">{escape(d["title"])}</option>' for d in deadlines
    )
    form = f"""<form id="mark-form">
<div class="field">
<label for="mark-title">Deadline</label>
<select id="mark-title" name="title">{options}</select>
</div>
<div class="field">
<label for="mark-mark">Your mark in % <span class="optional">(optional)</span></label>
<input id="mark-mark" name="mark_percent" inputmode="decimal" autocomplete="off">
</div>
<div class="field">
<label for="mark-weight">Worth % of the final mark <span class="optional">(optional)</span></label>
<input id="mark-weight" name="weight_percent" inputmode="decimal" autocomplete="off" aria-describedby="mark-weight-hint">
<p id="mark-weight-hint" class="hint">Leave it empty to keep the weight it has. A mark also marks the deadline done.</p>
</div>
<button type="submit">Save mark</button>
</form>"""
    if grades:
        summaries = "".join(_grade_summary(report) for report in grades)
    else:
        summaries = '<p class="empty">Give your deadlines a subject to see a summary for each subject.</p>'
    return f'<div id="grades">{form}{summaries}</div>'


def _percent_text(value) -> str:
    return "not set" if value is None else f"{tools._number_text(value)}%"


def _grade_summary(report: dict) -> str:
    """One subject: what is earned, what is still to come, each band, any warnings and each item."""
    bands = "".join(
        f'<li class="band {escape(report["bands"][key]["result"])}">{escape(tools._band_sentence(report["bands"][key]))}</li>'
        for key in BAND_KEYS
    )
    warnings = "".join(f'<p class="grade-warning">{escape(warning)}</p>' for warning in report["warnings"])
    rows = "".join(
        f'<tr><td><span class="title">{escape(item["title"])}</span></td>'
        f'<td>{escape(_percent_text(item["weight_percent"]))}</td>'
        f'<td>{escape(_percent_text(item["mark_percent"]))}</td></tr>'
        for item in report["items"]
    )
    earned = tools._number_text(report["earned_percent"])
    still = tools._number_text(report["still_to_come_percent"])
    return (
        f'<article class="grade-summary"><h3>{escape(report["subject"])}</h3>'
        f'<p class="summary">Earned so far: {escape(earned)}% of the final mark. Still to come: {escape(still)}%.</p>'
        f'{warnings}<ul class="bands">{bands}</ul>'
        '<table><caption class="visually-hidden">Weights and marks for this subject</caption>'
        '<thead><tr><th scope="col">Task</th><th scope="col">Weight</th><th scope="col">Mark</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></article>"
    )


def deadline_table(deadlines: list[dict], now: datetime, website: bool = False) -> str:
    """Every deadline, soonest first, with Mark done, Edit and Delete buttons. Finished ones are greyed.

    With no deadlines, it suggests the outline import, or on the website
    (which has no import yet) the example deadlines.
    """
    if not deadlines:
        if website:
            return (
                '<div id="deadline-table"><p class="empty">You have no deadlines saved yet. Add one below, '
                'or try "Add example deadlines" at the bottom of this page.</p></div>'
            )
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
    buttons += _edit_button(deadline)
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


def _edit_button(deadline: dict) -> str:
    """The Edit button for one deadline. It carries what the Edit box starts with, escaped like _button."""
    title = escape(deadline["title"])
    return (
        f'<button type="button" class="secondary" data-edit data-title="{title}" '
        f'data-due="{escape(deadline["due_date"])}" data-subject="{escape(deadline["subject"])}">'
        f'Edit<span class="visually-hidden">: {title}</span></button>'
    )


# The picker's value for "My university is not listed". import.js then builds the real
# session code ("CUSTOM:2027-03-01:12:6:1", see calendars.py) from the fields below.
CUSTOM_CHOICE = "CUSTOM"

CUSTOM_FIELDS = f"""<fieldset id="custom-field" class="field" hidden>
<legend>Your session's dates</legend>
<p class="hint">Groot does not have your university's calendar, so tell it how your session runs. Your subject outline or your university's key dates page has these.</p>
<div class="field">
<label for="custom-week1">Any day in week 1</label>
<input id="custom-week1" type="date">
</div>
<div class="field">
<label for="custom-weeks">Number of teaching weeks</label>
<input id="custom-weeks" type="number" min="1" max="{calendars.MAX_CUSTOM_WEEKS}" value="12" inputmode="numeric">
</div>
<div class="field">
<label for="custom-break-after">The mid-session break comes after week <span class="optional">(0 if there is no break, or if the break weeks keep their numbers)</span></label>
<input id="custom-break-after" type="number" min="0" max="{calendars.MAX_CUSTOM_WEEKS - 1}" value="0" inputmode="numeric">
</div>
<div class="field">
<label for="custom-break-weeks">How many weeks the break lasts</label>
<input id="custom-break-weeks" type="number" min="0" max="{calendars.MAX_BREAK_WEEKS}" value="0" inputmode="numeric">
</div>
<p class="hint">For a session you type yourself, Groot does not know the exam dates or the public holidays.</p>
<p id="custom-message" class="message" role="status"></p>
</fieldset>"""


def _session_picker(sessions: dict, custom: bool = True, selected: str | None = None) -> str:
    """The options of the university and session picker, grouped by country, then university.

    The student's own country (tools.PLACE) comes first, so a student in
    Singapore sees NUS, NTU and SMU at the top. Unless selected names a
    session, it starts on an empty choice on purpose. Each university counts
    its weeks differently, so a wrong guess would give wrong dates, and the
    student has to pick. import.js remembers their pick for next time.
    Each option starts with the university's short name ("NUS AY2026/27
    Semester 2"), so a closed picker on a phone still says which university.
    It also carries its university, which import.js uses to show only the
    extra fields that university can use. custom=False leaves out "My
    university is not listed", which needs the import page's extra fields.
    """
    groups = ""
    home_first = sorted(
        calendars.UNIVERSITIES.items(),
        key=lambda item: region.COUNTRIES[item[1]["country"]]["name"] != tools.PLACE["name"],  # sorted keeps the order otherwise
    )
    for key, university in home_first:
        country = region.COUNTRIES[university["country"]]["name"]
        options = "".join(
            f'<option value="{escape(code)}" data-university="{escape(key)}"{" selected" if code == selected else ""}>'
            f'{escape(university["name"])} {escape(info["name"])}</option>'
            for code, info in sessions.items()
            if info["university"] == key
        )
        if options:
            groups += f'<optgroup label="{escape(country)}: {escape(university["full_name"])}">{options}</optgroup>'
    # A student anywhere else types their own session's dates into the fields below the picker
    if custom:
        groups += (
            '<optgroup label="Another university">'
            f'<option value="{CUSTOM_CHOICE}" data-university="other">My university is not listed</option>'
            "</optgroup>"
        )
    return '<option value="">Choose your university and session</option>' + groups


def _finished_warning(finished: list[str]) -> str:
    """A warning naming the universities whose calendars in Groot have run out, or "" if none have."""
    if not finished:
        return ""
    if len(finished) == 1:
        which = f"calendar for {escape(finished[0])} has"
    else:
        names = ", ".join(escape(name) for name in finished[:-1]) + f" and {escape(finished[-1])}"
        which = f"calendars for {names} have"
    return (
        f'<p class="warning">Groot\'s {which} run out, because every session it knows there has finished. '
        "Update Groot to get the next sessions.</p>"
    )


def import_page(sessions: dict, finished: list[str]) -> str:
    """The outline drop box.

    sessions is calendars.open_sessions(today), so the picker only offers
    sessions that have not finished, and finished is
    calendars.finished_universities(today), which the page warns about.

    The outline picker accepts every file ending documents.py reads, and the
    hint lists them, so the page always matches what the reader can do.
    documents.py is imported here, not at the top, because it needs the
    document-reading libraries, which the home page (and the website) does not.
    """
    from deadline_agent import documents

    body = f"""<header class="top">
<p><a href="/groot">Back to your deadlines</a></p>
<h1>Import from outlines</h1>
<p class="tagline">Drop in your subject outlines, check the deadlines Groot finds, then save the ones you want.</p>
</header>
<main>
<section aria-labelledby="files-heading">
<h2 id="files-heading">1. Choose your university and files</h2>
<div class="field">
<label for="session-select">Your university and session</label>
<select id="session-select" aria-describedby="session-hint">{_session_picker(sessions)}</select>
<p id="session-hint" class="hint">Groot turns a week number, like "due in week 7", into a real date with this university's official calendar. Sessions that have finished are not listed.</p>
</div>
{CUSTOM_FIELDS}
{_finished_warning(finished)}
<div id="drop-zone" class="drop-zone">
<p class="drop-title">Drag your subject outlines here, or</p>
<input id="outline-input" class="visually-hidden" type="file" accept="{escape(documents.HTML_ACCEPT)}" multiple aria-describedby="outline-hint">
<label for="outline-input" class="button">Choose outline files</label>
<p id="outline-hint" class="hint">1 to 8 outlines, each up to 10 MB. {escape(documents.describe_supported())}</p>
<p class="hint">No outline to hand? <a href="/groot/sample-outline">Download a made-up sample outline</a>, then drop it in to see how the import works.</p>
</div>
<p id="file-message" class="message" role="status"></p>
<ul id="outline-list" class="file-list"></ul>
<div class="field" id="timetable-field" hidden>
<label for="timetable-input">Your UTS timetable <span class="optional">(optional PDF)</span></label>
<input id="timetable-input" type="file" accept=".pdf,application/pdf" aria-describedby="timetable-hint">
<button type="button" id="timetable-clear" class="secondary">Remove timetable</button>
<p id="timetable-hint" class="hint">Groot uses it to find the day and time of your tutorials. Only UTS timetables can be read so far.</p>
</div>
<div class="field" id="canvas-field" hidden>
<label for="canvas-input">Canvas calendar feed link <span class="optional">(optional)</span></label>
<input id="canvas-input" type="url" autocomplete="off" spellcheck="false" aria-describedby="canvas-hint">
<p id="canvas-hint" class="hint">In Canvas, open Calendar, then Calendar Feed, and copy the link. Groot reads it once and never saves it. Keep it private, because anyone with the link can see your calendar.</p>
</div>
</section>
<section aria-labelledby="preview-heading">
<h2 id="preview-heading">2. Preview</h2>
{"".join(f'<p class="warning">{escape(warning, quote=False)}</p>' + chr(10) for warning in import_warnings()).rstrip()}
<p id="request-count">Choose your university and session to preview.</p>
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
<link rel="icon" href="/groot/static/icon-32.png" type="image/png">
<link rel="stylesheet" href="/groot/static/groot.css">
<script type="module" src="/groot/static/{script}"></script>
</head>
<body data-ai="{escape(model_choice.ai_name())}">
{body}
</body>
</html>
"""
