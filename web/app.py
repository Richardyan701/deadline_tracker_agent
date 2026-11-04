"""Groot's web pages and their JSON API, on the same server as ADK's chat.

build_app() makes the FastAPI app that `adk web` runs (the chat at /dev-ui/)
and adds Groot's routes under /groot:

    GET  /groot               home page: heads up, due soon, all deadlines, add form, grades. Never uses Gemini.
    GET  /groot/import        the outline drop box
    POST /groot/api/add       add a deadline          JSON {"title", "due_date", "subject"}
    POST /groot/api/done      mark a deadline done    JSON {"title"}
    POST /groot/api/delete    delete a deadline       JSON {"title"}
    POST /groot/api/mark      save a mark or weight   JSON {"title", "mark_percent", "weight_percent"}
    POST /groot/api/export    download deadlines.ics  JSON {}
    POST /groot/api/preview   read outlines (Gemini)  multipart form, see uploads.py
    POST /groot/api/save      save the ticked rows    JSON {"rows": [{"title", "due_date", "subject", "weight_percent"}]}

Every change goes through the tools in deadline_agent/tools.py, so the file
lock, the safe saves and the backups work exactly as they do in the chat.
Each API answer is JSON with "status" ("success" or "error") and a
"message", except a successful export, which is the calendar file itself.

Any website open in the same browser can send requests to 127.0.0.1, so
every POST checks two things before it reads anything:

1. The Origin header must be Groot's own address. The browser sets it on
   every POST, and a web page cannot change it.
2. The content type must be the one the route expects. A page on another
   site cannot send JSON here without the browser asking this server first,
   and this server never says yes.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from google.adk.cli.fast_api import get_fast_api_app

from deadline_agent import importer, tools, uts_calendar

from . import Refused, pages, preview, uploads

# Only this computer can reach the server, and the port is the one adk web uses
HOST = "127.0.0.1"
PORT = 8000
# The addresses Groot's pages are opened at. Both names mean this computer.
OWN_ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}

# The folder that holds deadline_agent, which ADK looks in for agents
PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Every file the pages load, with its content type. Naming the type here means
# Windows' own file type settings, which sometimes call .js plain text, never matter.
STATIC_FILES = {
    "groot.css": "text/css",
    "common.js": "text/javascript",
    "home.js": "text/javascript",
    "import.js": "text/javascript",
}

DEFAULT_SESSION = "SPR2026"
SAVE_FIELDS = {"title", "due_date", "subject"}

PAGE_HEADERS = {
    # Only Groot's own files may run or style the page, and no other site may
    # show it inside a frame (which could trick the student into clicking a button)
    "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",  # always show the deadlines as they are now
}

router = APIRouter(prefix="/groot")


# ---------- the safety checks ----------


def check_sender(request: Request, content_type: str) -> None:
    """Refuse a request unless it came from Groot's own page with the expected content type."""
    if request.headers.get("origin") not in OWN_ORIGINS:
        raise Refused(403, "This request did not come from Groot's own page, so it was refused.")
    # "application/json; charset=utf-8" counts as "application/json"
    sent_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if sent_type != content_type:
        raise Refused(415, f"Groot only accepts {content_type} here.")


async def json_from_groot(request: Request) -> dict:
    """The JSON object one of Groot's pages sent, read only after the safety checks pass."""
    check_sender(request, "application/json")
    try:
        data = await request.json()
    except ValueError:  # not JSON, or not UTF-8 text
        raise Refused(400, "That request was not valid JSON.") from None
    if not isinstance(data, dict):
        raise Refused(400, "That request must be a JSON object.")
    return data


async def upload_from_groot(request: Request) -> uploads.Upload:
    """The drop box's files and fields, read into memory only after the safety checks pass."""
    check_sender(request, "multipart/form-data")
    return await uploads.read_upload(request.headers["content-type"], request.stream())


def outline_reader() -> preview.OutlineReader:
    """The function the preview uses to read one outline with Gemini.

    The tests swap this for a fake (with app.dependency_overrides), so they
    never send anything to Gemini.
    """
    return preview.read_with_gemini


async def _refused(request: Request, error: Refused) -> JSONResponse:
    return JSONResponse({"status": "error", "message": str(error)}, status_code=error.status_code)


# ---------- the pages ----------


def _page(html: str) -> HTMLResponse:
    return HTMLResponse(html, headers=PAGE_HEADERS)


@router.get("", response_class=HTMLResponse)
def home() -> HTMLResponse:
    """The home page. It only reads the deadlines file, so it never uses Gemini."""
    deadlines = tools.list_deadlines()["deadlines"]
    grades = tools._all_grade_reports()
    return _page(pages.home_page(tools.get_reminders(), deadlines, tools._now(), grades))


@router.get("/import", response_class=HTMLResponse)
def import_page() -> HTMLResponse:
    """The outline drop box. Nothing is sent to Gemini until the student clicks Preview."""
    return _page(pages.import_page(uts_calendar.SESSIONS, DEFAULT_SESSION))


@router.get("/static/{name}")
def static_file(name: str) -> FileResponse:
    if name not in STATIC_FILES:
        raise HTTPException(status_code=404)
    return FileResponse(STATIC_DIR / name, media_type=STATIC_FILES[name])


# ---------- the home page's actions ----------


@router.post("/api/add")
def add(data: dict = Depends(json_from_groot)) -> dict:
    """Add a deadline. add_deadline understands words like "next friday 5pm" and explains any problem."""
    return tools.add_deadline(data.get("title"), data.get("due_date"), data.get("subject"))


@router.post("/api/done")
def done(data: dict = Depends(json_from_groot)) -> dict:
    return tools.mark_done(data.get("title"))


@router.post("/api/delete")
def delete(data: dict = Depends(json_from_groot)) -> dict:
    return tools.delete_deadline(data.get("title"))


@router.post("/api/mark")
def mark(data: dict = Depends(json_from_groot)) -> dict:
    """Save a mark, a weight or both with set_mark, which checks each is a number from 0 to 100."""
    return tools.set_mark(data.get("title"), data.get("mark_percent"), data.get("weight_percent"))


@router.post("/api/export", dependencies=[Depends(json_from_groot)])
def export() -> Response:
    """Save the calendar file with export_calendar, then send it to the browser to download."""
    result = tools.export_calendar()
    if result["status"] == "error" or result["exported"] == 0:
        return JSONResponse(result)  # no file to download, so the page shows the tool's message
    return Response(
        tools._calendar_file().read_bytes(),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="deadlines.ics"'},
    )


# ---------- the outline drop box ----------


@router.post("/api/preview")
def preview_upload(
    upload: uploads.Upload = Depends(upload_from_groot),
    read: preview.OutlineReader = Depends(outline_reader),
) -> dict:
    """Read the outlines (one Gemini request each) and return the rows to check. Nothing is saved."""
    return preview.build(upload, read)


@router.post("/api/save")
def save(data: dict = Depends(json_from_groot)) -> dict:
    """Save the rows the student ticked, each through add_deadline, and return one result per row."""
    rows = data.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) and SAVE_FIELDS <= row.keys() for row in rows):
        raise Refused(400, 'Each row to save needs a "title", a "due_date" and a "subject".')
    # weight_percent is optional, so rows from an older page without it still save
    results = importer.save_rows(rows)
    saved = sum(result["status"] == "success" for result in results)
    if not rows:
        message = "No rows were ticked, so nothing was saved."
    elif saved == len(rows):
        message = f"Saved {tools._plural(saved, 'deadline')} to your list."
    else:
        message = f"Saved {saved} of {len(rows)} deadlines. Each row that was not saved says why."
    return {"status": "success", "message": message, "results": results}


# ---------- putting it together ----------


def add_groot(app: FastAPI) -> None:
    """Add Groot's pages and API to an app."""
    app.include_router(router)
    app.add_exception_handler(Refused, _refused)


@asynccontextmanager
async def _say_where_to_go(app: FastAPI):
    """Print where to open Groot once the server has started."""
    print(
        f"\nAgent Groot is ready. Open http://{HOST}:{PORT}/groot in your browser."
        f"\nThe chat with Groot is at http://{HOST}:{PORT}{pages.CHAT_PATH}"
        "\nTo stop Groot, press Ctrl+C in this window.\n",
        flush=True,
    )
    yield


def build_app() -> FastAPI:
    """ADK's own app, the one `adk web` runs, with Groot's pages added.

    The chat stays at /dev-ui/ and Groot's pages live at /groot, on one
    server and one port. bind_host also turns on ADK's guard against "DNS
    rebinding", a trick where a website points its own name at 127.0.0.1
    to reach this server.
    """
    app = get_fast_api_app(
        agents_dir=str(PROJECT_DIR),
        web=True,
        host=HOST,
        bind_host=HOST,
        port=PORT,
        lifespan=_say_where_to_go,
    )
    add_groot(app)
    return app
