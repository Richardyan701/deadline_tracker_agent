"""Agent Groot's own web pages, served on the same server as ADK's chat.

Start them with:  python -m web
(on Windows:      .venv\\Scripts\\python.exe -m web)

Then open http://127.0.0.1:8000/groot for Groot's pages, or
http://127.0.0.1:8000/dev-ui/ for the chat.

    app.py      the routes, the safety checks and build_app()
    pages.py    the HTML of the two pages
    uploads.py  reads uploaded files into memory, never onto disk
    preview.py  turns outlines, a timetable and a Canvas feed into review rows
    static/     the CSS and JavaScript the pages load
"""


class Refused(Exception):
    """A request Groot will not handle, with a message that is safe to show the student.

    status_code is the HTTP status sent back, for example 403 when the
    request did not come from Groot's own page.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
