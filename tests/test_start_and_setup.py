"""Tests for the one-click start files and the setup checker (deadline_agent/check_setup.py).

No API key and no internet needed. start_groot.sh is run for real, in a
temporary copy of the project, where .venv/bin/python is a stand-in that runs
a tiny web server instead of Groot's web app, and xdg-open and open are
stand-ins that only write down what they were asked to open. start_groot.bat
cannot run here, so only its text is checked. The setup checker is tested
check by check, with temporary files and fake environments.
"""

import ast
import http.server
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import zoneinfo
from importlib import metadata
from pathlib import Path

import httpx
import pytest
from google import genai

from deadline_agent import check_setup
from deadline_agent.friendly_errors import BAD_KEY

PROJECT = Path(__file__).resolve().parent.parent
START_SH = PROJECT / "start_groot.sh"
START_BAT = PROJECT / "start_groot.bat"
URL = "http://127.0.0.1:8000/groot"  # Groot's home page, which the start files open
FAKE_KEY = "not-a-real-key-123"

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="start_groot.sh is for Linux and macOS")


def port_8000_is_free():
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=5):
            return False
    except ConnectionRefusedError:
        return True


def wait_for(condition, seconds=30):
    """Check condition() ten times a second until it is true. False if it never was."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


# ---------- start_groot.sh, run for real ----------


def fake_project(tmp_path, server_command, home_page=True):
    """A temporary project folder with start_groot.sh, a .env and a stand-in .venv/bin/python.

    Asked to start Groot's web app (python -m web), the stand-in writes down
    how it was asked in server_command.txt and runs server_command instead.
    Anything else, like the script asking "is Groot's page answering yet?",
    goes to the real Python. A web server started in the project folder
    answers /groot with the file called groot, which is only there if home_page is true.
    """
    project = tmp_path / "project"
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / "deadline_agent").mkdir()
    (project / "deadline_agent" / ".env").write_text(f"GOOGLE_API_KEY={FAKE_KEY}\n")
    if home_page:
        (project / "groot").write_text("Groot's home page\n")
    shutil.copy(START_SH, project / "start_groot.sh")
    python = project / ".venv" / "bin" / "python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "-m" ] && [ "$2" = "web" ]; then\n'
        f'    echo "$*" > "{tmp_path}/server_command.txt"\n'
        f"    {server_command}\n"
        "fi\n"
        f'exec "{sys.executable}" "$@"\n'
    )
    python.chmod(0o755)
    return project


def fake_commands(tmp_path, system="Linux"):
    """Stand-ins for xdg-open and open that write down what they open, and for uname. Returns a PATH."""
    commands = {
        "xdg-open": f'echo "xdg-open $*" >> "{tmp_path}/opened.txt"',
        "open": f'echo "open $*" >> "{tmp_path}/opened.txt"',
        "uname": f"echo {system}",
    }
    folder = tmp_path / "bin"
    folder.mkdir()
    for name, line in commands.items():
        (folder / name).write_text(f"#!/usr/bin/env bash\n{line}\n")
        (folder / name).chmod(0o755)
    return f"{folder}{os.pathsep}{os.environ['PATH']}"


@pytest.fixture
def start(tmp_path):
    """Runs a project's start_groot.sh from another folder, like a double click does.

    Returns (process, output file). Anything still running is stopped afterwards.
    """
    processes = []

    def run(project, path):
        output = tmp_path / "output.txt"
        with output.open("w") as out:
            process = subprocess.Popen(
                [str(project / "start_groot.sh")],
                cwd=tmp_path,
                env={**os.environ, "PATH": path},
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # its own process group, so "Ctrl+C" below reaches only it
            )
        processes.append(process)
        return process, output

    yield run
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)  # anything left over, so port 8000 is free again
        except ProcessLookupError:
            pass
        process.wait()


@needs_bash
@pytest.mark.parametrize("system, opener", [("Linux", "xdg-open"), ("Darwin", "open")])
def test_start_script_starts_groot_opens_the_browser_and_stops_on_ctrl_c(tmp_path, start, system, opener):
    if not port_8000_is_free():
        pytest.skip("port 8000 is in use (is Groot running?), so this test cannot run")
    project = fake_project(tmp_path, f'exec "{sys.executable}" -m http.server 8000 --bind 127.0.0.1')
    process, output = start(project, fake_commands(tmp_path, system))

    assert wait_for(lambda: "Press Ctrl+C to stop it." in output.read_text()), output.read_text()
    assert f"Groot is running at {URL}" in output.read_text()
    # Groot's web app, started the antivirus safe way, through Python, from the project folder
    assert (tmp_path / "server_command.txt").read_text() == "-m web\n"
    assert wait_for(lambda: (tmp_path / "opened.txt").exists())
    assert (tmp_path / "opened.txt").read_text() == f"{opener} {URL}\n"  # the home page, not only the server

    os.killpg(process.pid, signal.SIGINT)  # what pressing Ctrl+C in the terminal does
    process.wait(timeout=15)
    assert port_8000_is_free()  # the server stopped too


@needs_bash
def test_start_script_waits_for_groots_home_page_not_just_any_answer(tmp_path, start):
    if not port_8000_is_free():
        pytest.skip("port 8000 is in use (is Groot running?), so this test cannot run")
    # The server answers, but only with "404 Not Found" until the home page is there
    project = fake_project(tmp_path, f'exec "{sys.executable}" -m http.server 8000 --bind 127.0.0.1', home_page=False)
    process, output = start(project, fake_commands(tmp_path))

    assert wait_for(lambda: not port_8000_is_free())
    time.sleep(3)  # several of the script's once a second checks
    assert "Groot is running" not in output.read_text()
    assert not (tmp_path / "opened.txt").exists()

    (project / "groot").write_text("Groot's home page\n")  # now /groot answers
    assert wait_for(lambda: (tmp_path / "opened.txt").exists())
    assert (tmp_path / "opened.txt").read_text() == f"xdg-open {URL}\n"


@needs_bash
def test_start_script_says_so_when_the_server_cannot_start(tmp_path, start):
    if not port_8000_is_free():
        pytest.skip("port 8000 is in use (is Groot running?), so this test cannot run")
    project = fake_project(tmp_path, 'echo "address already in use" >&2; exit 3')
    process, output = start(project, fake_commands(tmp_path))

    assert process.wait(timeout=30) == 1
    assert "Groot could not start. Read the messages above" in output.read_text()
    assert not (tmp_path / "opened.txt").exists()  # no browser for a server that is not there


@needs_bash
@pytest.mark.parametrize("missing", [".venv", "deadline_agent/.env"])
def test_start_script_asks_for_setup_first(tmp_path, missing):
    project = fake_project(tmp_path, "exit 0")
    target = project / missing
    shutil.rmtree(target) if target.is_dir() else target.unlink()

    result = subprocess.run([str(project / "start_groot.sh")], cwd=tmp_path, capture_output=True, text=True, timeout=30)

    assert result.returncode == 1
    assert result.stdout == "Groot is not set up yet, so please run ./setup.sh first.\n"
    assert not (tmp_path / "server_command.txt").exists()


@needs_bash
def test_start_script_is_executable_with_unix_line_endings():
    assert os.access(START_SH, os.X_OK)
    assert b"\r" not in START_SH.read_bytes()


def test_start_bat_uses_windows_line_endings_and_the_antivirus_safe_command():
    data = START_BAT.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n")  # every line ends with CRLF
    text = data.decode("ascii")
    # Groot's web app, started through Python, never adk.exe or the old chat-only server
    assert '\r\n".venv\\Scripts\\python.exe" -m web\r\n' in text
    assert "google.adk.cli" not in text and "adk.exe" not in text
    # It waits for the home page itself, and an error page from another program does not count
    curl = next(line for line in text.splitlines() if line.startswith("curl.exe "))
    assert "--fail" in curl and "--retry-connrefused" in curl
    assert curl.endswith(f" {URL}")
    assert f'start "" {URL}\r\n' in text
    assert f"echo Groot is running at {URL}\r\n" in text
    assert "Groot is not set up yet, so please run setup_windows.bat first." in text
    assert "Press Ctrl+C in this window to stop it." in text


def test_the_start_files_and_the_web_app_agree_on_the_address():
    from web import app as web_app

    assert URL == f"http://{web_app.HOST}:{web_app.PORT}/groot"
    assert f'URL="{URL}"' in START_SH.read_text(encoding="utf-8")
    assert ".venv/bin/python -m web &" in START_SH.read_text(encoding="utf-8")


# ---------- the setup checker, check by check ----------


def free_port():
    """A port number that nothing is using right now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def write_requirements(tmp_path, monkeypatch, text):
    path = tmp_path / "requirements.txt"
    path.write_text(text)
    monkeypatch.setattr(check_setup, "REQUIREMENTS", path)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """A temporary deadline_agent/.env (not created yet)."""
    path = tmp_path / ".env"
    monkeypatch.setattr(check_setup, "ENV_FILE", path)
    return path


@pytest.fixture
def deadlines_file(tmp_path, monkeypatch):
    """A temporary deadlines.json (not created yet)."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    return path


def test_python_311_or_newer_passes():
    assert check_setup.check_python((3, 11, 0)) == (True, "Python 3.11.0", "")
    assert check_setup.check_python()[0] is True  # the Python running these tests


@pytest.mark.parametrize("version", [(3, 10, 12), (3, 9, 6)])
def test_older_python_fails_with_a_fix(version):
    passed, found, fix = check_setup.check_python(version)
    shown = ".".join(map(str, version))

    assert (passed, found) == (False, f"Python {shown} is too old, Groot needs 3.11 or newer")
    assert fix == "Install Python 3.11 or newer from python.org, then run the setup script again."


def test_the_oldest_python_allowed_is_one_every_pinned_package_supports():
    # Each installed package says which Pythons it supports. If the setup allowed an older one,
    # pip would stop half way through the setup (python-multipart 0.0.33 needs 3.11, for example).
    from packaging.specifiers import SpecifierSet

    oldest = ".".join(map(str, check_setup.MIN_PYTHON))
    pins = [line.split("==")[0] for line in (PROJECT / "requirements.txt").read_text().split() if "==" in line]
    for name in pins:
        supported = metadata.metadata(name).get("Requires-Python") or ""
        assert SpecifierSet(supported).contains(oldest), f"{name} needs Python {supported}"
    # The setup scripts check for the same version as the checker
    check = f"sys.version_info >= {check_setup.MIN_PYTHON}"
    assert check in (PROJECT / "setup.sh").read_text(encoding="utf-8")
    assert check in (PROJECT / "setup_windows.bat").read_text(encoding="utf-8")


def test_packages_at_the_right_versions_pass(tmp_path, monkeypatch):
    version = metadata.version("pytest")
    write_requirements(tmp_path, monkeypatch, f"# what the tests need\n\npytest=={version}  # pinned\n")

    assert check_setup.check_packages() == (True, f"Packages: pytest {version}", "")


def test_missing_or_wrong_packages_fail(tmp_path, monkeypatch):
    write_requirements(tmp_path, monkeypatch, "pytest==0.0.1\nsurely-not-a-real-package-for-groot==1.0\n")

    passed, found, fix = check_setup.check_packages()

    assert not passed
    assert found == (
        f"Packages: pytest is {metadata.version('pytest')} but requirements.txt needs 0.0.1, "
        "surely-not-a-real-package-for-groot is not installed"
    )
    assert "setup.sh" in fix and "the Python in .venv" in fix


def test_missing_env_file_fails(env_file):
    passed, found, fix = check_setup.check_api_key()

    assert (passed, found) == (False, "deadline_agent/.env is missing")
    assert "paste your Gemini API key" in fix


@pytest.mark.parametrize(
    "text, found",
    [
        ("GOOGLE_GENAI_USE_ENTERPRISE=0\n", "deadline_agent/.env has no GOOGLE_API_KEY"),
        ("GOOGLE_API_KEY=\n", "deadline_agent/.env has no GOOGLE_API_KEY"),
        (f"# GOOGLE_API_KEY={FAKE_KEY}\n", "deadline_agent/.env has no GOOGLE_API_KEY"),
        ("GOOGLE_API_KEY=paste-your-gemini-api-key-here\n", "GOOGLE_API_KEY in deadline_agent/.env is still the example text"),
    ],
)
def test_env_file_without_a_real_key_fails(env_file, text, found):
    env_file.write_text(text)

    assert check_setup.check_api_key()[:2] == (False, found)


@pytest.mark.parametrize(
    "data",
    [
        f"GOOGLE_GENAI_USE_ENTERPRISE=0\nGOOGLE_API_KEY={FAKE_KEY}\n".encode(),  # what setup.sh writes
        f"GOOGLE_GENAI_USE_ENTERPRISE=0\r\nGOOGLE_API_KEY={FAKE_KEY}\r\n".encode(),  # what setup_windows.bat writes
        f'export GOOGLE_API_KEY="{FAKE_KEY}"  # my key\n'.encode(),
    ],
)
def test_env_file_with_a_key_passes_without_showing_it(env_file, data):
    env_file.write_bytes(data)

    assert check_setup.check_api_key() == (True, "deadline_agent/.env has a GOOGLE_API_KEY (the key is not shown)", "")
    assert check_setup.read_api_key() == FAKE_KEY  # the same key ADK would load


def test_env_file_that_is_not_plain_text_fails(env_file):
    env_file.write_text(f"GOOGLE_API_KEY={FAKE_KEY}\n", encoding="utf-16")  # what some Windows tools save

    assert check_setup.check_api_key()[:2] == (False, "deadline_agent/.env could not be read")


def test_env_file_cannot_be_checked_without_python_dotenv(env_file, monkeypatch):
    env_file.write_text(f"GOOGLE_API_KEY={FAKE_KEY}\n")
    monkeypatch.setitem(sys.modules, "dotenv", None)  # as if python-dotenv was not installed

    assert check_setup.check_api_key()[:2] == (False, "deadline_agent/.env could not be checked without python-dotenv")


class FakeWebServer(http.server.BaseHTTPRequestHandler):
    """Answers /list-apps the way adk web does, with the names in server.apps (None means "not found")."""

    def do_GET(self):
        if self.path != "/list-apps" or self.server.apps is None:
            self.send_error(404)
            return
        body = json.dumps(self.server.apps).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output quiet
        pass


@pytest.fixture
def web_server(monkeypatch):
    """Starts a small web server on a free port, and points the checker's port check at it."""
    servers = []

    def run(apps):
        server = http.server.HTTPServer(("127.0.0.1", 0), FakeWebServer)
        server.apps = apps
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        monkeypatch.setattr(check_setup, "PORT", server.server_address[1])

    yield run
    for server in servers:
        server.shutdown()
        server.server_close()


def test_free_port_passes(monkeypatch):
    monkeypatch.setattr(check_setup, "PORT", free_port())

    assert check_setup.check_port() == (True, f"Port {check_setup.PORT} is free", "")


def test_port_already_serving_groot_passes(web_server):
    web_server(["deadline_agent"])

    assert check_setup.check_port() == (True, f"Groot is already running at http://127.0.0.1:{check_setup.PORT}", "")


@pytest.mark.parametrize("apps", [None, ["some_other_agent"], {"not": "a list"}])
def test_port_used_by_another_program_fails(web_server, apps):
    web_server(apps)

    passed, found, fix = check_setup.check_port()

    assert (passed, found) == (False, f"Another program is using port {check_setup.PORT}")
    assert fix.startswith(f"Close the program using port {check_setup.PORT}")


@pytest.fixture
def no_time_zones(tmp_path, monkeypatch):
    """As if this computer had no time zone database: nothing to search, and no tzdata package."""
    zoneinfo.reset_tzpath(to=[str(tmp_path)])
    for name in [name for name in sys.modules if name.startswith("tzdata.")] + ["tzdata"]:
        monkeypatch.setitem(sys.modules, name, None)
    yield
    zoneinfo.reset_tzpath()  # back to normal


def test_sydney_time_zone_passes():
    assert check_setup.check_timezone() == (True, "The Australia/Sydney time zone is available", "")


def test_missing_time_zone_fails(no_time_zones):
    passed, found, fix = check_setup.check_timezone()

    assert (passed, found) == (False, "Python cannot find the Australia/Sydney time zone")
    assert "tzdata" in fix


def test_no_deadlines_file_yet_passes(deadlines_file):
    assert check_setup.check_deadlines_file() == (
        True,
        "No deadlines saved yet (deadlines.json is made when you add your first one)",
        "",
    )


def test_valid_deadlines_file_passes(deadlines_file):
    deadlines_file.write_text(json.dumps([
        {"title": "Essay", "due_date": "2026-11-20", "subject": "Writing", "done": False},
        {"title": "Quiz 2", "due_date": "2026-11-13 17:00", "subject": "", "done": True},
    ]))

    assert check_setup.check_deadlines_file() == (True, f"{deadlines_file} holds 2 deadlines and reads fine", "")


@pytest.mark.parametrize("text", ["{not json", '[{"title": "Essay"}]', '[{"title": "Essay", "due_date": "friday", "subject": "", "done": false}]'])
def test_broken_deadlines_file_fails_and_is_left_alone(deadlines_file, text):
    deadlines_file.write_text(text)
    files_before = sorted(os.listdir(deadlines_file.parent))

    passed, found, fix = check_setup.check_deadlines_file()

    assert (passed, found) == (False, f"{deadlines_file} cannot be read or is not a valid list of deadlines")
    assert deadlines_file.read_text() == text  # never changed
    assert sorted(os.listdir(deadlines_file.parent)) == files_before  # and no backup copy was made


# ---------- the whole checker ----------


@pytest.fixture
def all_good(tmp_path, monkeypatch, env_file, deadlines_file):
    """A fake environment where every check passes."""
    env_file.write_text(f"GOOGLE_GENAI_USE_ENTERPRISE=0\nGOOGLE_API_KEY={FAKE_KEY}\n")
    write_requirements(tmp_path, monkeypatch, f"pytest=={metadata.version('pytest')}\n")
    monkeypatch.setattr(check_setup, "PORT", free_port())


@pytest.fixture
def no_internet(monkeypatch):
    """Fails the test if the checker tries to reach anything but this computer. Returns where it connected."""
    addresses = []
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        addresses.append(address)
        assert address[0] == "127.0.0.1", f"tried to reach {address}"
        return real_connect(self, address)

    def getaddrinfo(host, *args, **kwargs):
        assert host == "127.0.0.1", f"tried to look up {host}"
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return addresses


def test_everything_passes_with_exit_code_0_and_no_internet(all_good, no_internet, capsys):
    assert check_setup.main([]) == 0

    output = capsys.readouterr().out
    assert output.count("✓ ") == 6 and "✗" not in output
    assert output.rstrip().endswith("All good! Start Groot with start_groot.bat (Windows) or ./start_groot.sh (Linux and macOS).")
    assert FAKE_KEY not in output
    assert no_internet == [("127.0.0.1", check_setup.PORT)]  # only the port check, on this computer


def test_a_failed_check_gives_exit_code_1_and_a_fix(all_good, env_file, capsys):
    env_file.unlink()

    assert check_setup.main([]) == 1

    output = capsys.readouterr().out
    assert "✗ deadline_agent/.env is missing\n    Fix: Run setup_windows.bat (Windows) or ./setup.sh (Linux and macOS)" in output
    assert output.rstrip().endswith("1 problem found. Follow each Fix above, then run this check again.")


@pytest.mark.parametrize(
    "encoding, expected",
    [
        ("utf-8", ("✓", "✗")),
        ("utf-16", ("✓", "✗")),
        ("cp1252", ("[OK]", "[X]")),  # what Windows uses when the output goes to a file
        ("cp437", ("[OK]", "[X]")),  # an old Windows console
        ("ascii", ("[OK]", "[X]")),
    ],
)
def test_marks_fall_back_to_plain_text_where_the_output_cannot_show_them(encoding, expected):
    stream = io.TextIOWrapper(io.BytesIO(), encoding=encoding)
    assert check_setup.marks(stream) == expected


def test_the_whole_checker_is_readable_on_an_old_windows_console(all_good, env_file, monkeypatch):
    env_file.unlink()  # so there is a cross as well as ticks
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp437", newline="\r\n")
    monkeypatch.setattr(sys, "stdout", console)

    assert check_setup.main([]) == 1

    console.flush()
    output = console.buffer.getvalue().decode("cp437")
    assert output.count("[OK] ") == 5
    assert "[X] deadline_agent/.env is missing\r\n    Fix: " in output
    assert "?" not in output  # no tick or cross was turned into a question mark


def test_the_checker_started_the_real_way_uses_plain_marks_on_an_old_console(tmp_path):
    result = run_checker(tmp_path, "-S", PYTHONIOENCODING="cp437")

    assert result.returncode == 1, result.stderr
    assert "[X] Packages: " in result.stdout
    assert "?" not in result.stdout


def test_an_old_python_stops_after_the_first_check(monkeypatch, capsys):
    real_check = check_setup.check_python
    monkeypatch.setattr(check_setup, "check_python", lambda: real_check((3, 9, 6)))

    assert check_setup.main([]) == 1

    output = capsys.readouterr().out
    assert "✗ Python 3.9.6 is too old, Groot needs 3.11 or newer" in output
    assert "Packages" not in output  # nothing else was tried


@pytest.fixture
def fake_gemini(monkeypatch):
    """Answers the checker's request to Gemini without the internet.

    Set reply to (status code, JSON body), or to an exception for a network
    failure. Every request the checker sent is kept in requests.
    """

    class FakeGemini:
        reply = (200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}, "finishReason": "STOP"}]})
        requests = []

    def answer(request):
        FakeGemini.requests.append(request)
        if isinstance(FakeGemini.reply, Exception):
            raise FakeGemini.reply
        status, body = FakeGemini.reply
        return httpx.Response(status, json=body)

    real_client = genai.Client

    def client(api_key, http_options):
        # The real google-genai client, with only the network swapped for answer()
        options = http_options.model_copy(update={"client_args": {"transport": httpx.MockTransport(answer)}})
        return real_client(api_key=api_key, http_options=options)

    monkeypatch.setattr(genai, "Client", client)
    return FakeGemini


def test_online_check_warns_first_and_sends_exactly_one_request(all_good, fake_gemini, capsys):
    assert check_setup.main(["--online"]) == 0

    output = capsys.readouterr().out
    warning = output.index("Now sending one real request to Gemini. This uses 1 of your 20 free requests for today.")
    assert warning < output.index("✓ Gemini answered, so your key works (gemini-3.5-flash)")
    assert len(fake_gemini.requests) == 1
    request = fake_gemini.requests[0]
    assert request.url.path.endswith("/models/gemini-3.5-flash:generateContent")  # Groot's own model
    assert request.headers["x-goog-api-key"] == FAKE_KEY  # the key from .env was used
    assert FAKE_KEY not in output  # but never shown


@pytest.mark.parametrize(
    "reply, found",
    [
        (
            (400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "details": [
                {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]}}),
            BAD_KEY,
        ),
        ((503, {"error": {"code": 503, "status": "UNAVAILABLE"}}), "Gemini answered with an error: 503 UNAVAILABLE"),
        (httpx.ConnectError("no internet"), "Could not reach Gemini (ConnectError)"),
    ],
)
def test_online_check_explains_what_went_wrong(all_good, fake_gemini, capsys, reply, found):
    fake_gemini.reply = reply

    assert check_setup.main(["--online"]) == 1

    assert f"✗ {found}\n    Fix: " in capsys.readouterr().out


def test_online_check_is_skipped_when_something_else_failed(all_good, env_file, fake_gemini, capsys):
    env_file.unlink()

    assert check_setup.main(["--online"]) == 1

    assert fake_gemini.requests == []  # no free request was used
    assert "The Gemini check was skipped, so no free request was used." in capsys.readouterr().out


# ---------- the checker started the real way, as python -m deadline_agent.check_setup ----------


def run_checker(tmp_path, *python_options, **env):
    """Run the checker in a new Python, the way a student does. Returns the finished process."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DEADLINES_FILE": str(tmp_path / "deadlines.json"), **env}
    return subprocess.run(
        [sys.executable, *python_options, "-m", "deadline_agent.check_setup"],
        cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


def test_checker_explains_missing_packages_instead_of_crashing(tmp_path):
    # -S starts Python without its installed packages, as if the setup stopped half way.
    # The checker must still start and say so, which is why deadline_agent/__init__.py imports nothing.
    result = run_checker(tmp_path, "-S")

    assert result.returncode == 1, result.stderr
    # Every package in requirements.txt is missing, in the same order as that file.
    names = [line.split("==")[0].strip() for line in (PROJECT / "requirements.txt").read_text().splitlines() if line.strip()]
    missing = ", ".join(f"{name} is not installed" for name in names)
    assert f"✗ Packages: {missing}" in result.stdout


def test_checker_explains_a_missing_time_zone_database(tmp_path):
    fake_site = tmp_path / "site"
    (fake_site / "tzdata").mkdir(parents=True)
    (fake_site / "tzdata" / "__init__.py").write_text("")  # a tzdata package with no time zones in it
    (tmp_path / "no_zones").mkdir()

    result = run_checker(
        tmp_path,
        PYTHONTZPATH=str(tmp_path / "no_zones"),
        PYTHONPATH=os.pathsep.join([str(fake_site), str(PROJECT)]),
    )

    assert result.returncode == 1, result.stderr
    assert "✗ Python cannot find the Australia/Sydney time zone" in result.stdout
    assert "✗ The deadlines file could not be checked without the Sydney time zone" in result.stdout


def test_the_checker_can_start_on_an_old_python():
    # Only the Python check runs on an old Python, but the whole file must still load there
    ast.parse((PROJECT / "deadline_agent" / "check_setup.py").read_text(encoding="utf-8"), feature_version=(3, 9))
