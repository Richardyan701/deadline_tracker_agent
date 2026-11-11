"""Checks that Agent Groot is set up, and says how to fix anything that is not.

Run it from the project folder:

    Windows:          .venv\\Scripts\\python.exe -m deadline_agent.check_setup
    Linux and macOS:  .venv/bin/python -m deadline_agent.check_setup

Each check prints a tick or a cross (or [OK] and [X] where the window cannot
show those two characters), and every cross comes with a one line fix. It
only reads files and never changes them. Nothing leaves your computer
unless you add --online, which sends one tiny real request to Gemini to prove
your key works. It exits with 0 when every check passes and 1 otherwise.

Only the Python check runs on a Python older than 3.11. So the code at the
top level here sticks to things old Pythons understand, and the other checks
import what they need inside their own functions.
"""

import argparse
import json
import socket
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PROJECT / "requirements.txt"
ENV_FILE = PROJECT / "deadline_agent" / ".env"
PORT = 8000

# The oldest Python that every package in requirements.txt supports. python-multipart 0.0.33,
# which reads the drop box's uploads, needs 3.11 (google-adk 2.11.0 itself only needs 3.10).
# setup.sh and setup_windows.bat check for the same version.
MIN_PYTHON = (3, 11)

# The pretend key in deadline_agent/.env.example
EXAMPLE_KEY = "paste-your-gemini-api-key-here"

RUN_SETUP = "Run setup_windows.bat (Windows) or ./setup.sh (Linux and macOS)"
USE_VENV = "and run this check with the Python in .venv"

TICK = "✓"
CROSS = "✗"
# Printed instead when the output cannot show the two above, for example a
# Windows console using an old code page, or output saved to a file as cp1252
PLAIN_TICK = "[OK]"
PLAIN_CROSS = "[X]"


# ---------- the checks ----------
#
# Each check returns (passed, what it found, how to fix it). The fix is "" when it passed.


def check_python(version=sys.version_info):
    """Python 3.11 or newer (MIN_PYTHON), the oldest that every package in requirements.txt supports."""
    shown = ".".join(str(part) for part in version[:3])
    if tuple(version[:2]) >= MIN_PYTHON:
        return True, f"Python {shown}", ""
    needed = ".".join(str(part) for part in MIN_PYTHON)
    return (
        False,
        f"Python {shown} is too old, Groot needs {needed} or newer",
        f"Install Python {needed} or newer from python.org, then run the setup script again.",
    )


def check_packages():
    """Every package in requirements.txt is installed, at exactly the version written there.

    Each line there is a pin like google-adk==2.11.0, so a line without == stops the check with an error.
    """
    from importlib import metadata

    found, problems = [], []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()  # leave out comments and blank lines
        if not line:
            continue
        name, wanted = (part.strip() for part in line.split("=="))
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            problems.append(f"{name} is not installed")
            continue
        if installed == wanted:
            found.append(f"{name} {installed}")
        else:
            problems.append(f"{name} is {installed} but requirements.txt needs {wanted}")
    if problems:
        return False, "Packages: " + ", ".join(problems), f"{RUN_SETUP} again, {USE_VENV}."
    return True, "Packages: " + ", ".join(found), ""


def read_api_key():
    """The GOOGLE_API_KEY in deadline_agent/.env, or "" if there is none.

    It is read with python-dotenv, the same way ADK reads the file when Groot
    starts, so the two always agree. The key is never printed.
    """
    from dotenv import dotenv_values

    return dotenv_values(ENV_FILE).get("GOOGLE_API_KEY") or ""


def check_api_key():
    """deadline_agent/.env exists and sets GOOGLE_API_KEY. The key itself is never shown."""
    if not ENV_FILE.is_file():
        return False, "deadline_agent/.env is missing", f"{RUN_SETUP} and paste your Gemini API key when it asks."
    try:
        key = read_api_key()
    except ImportError:  # python-dotenv comes with google-adk
        return False, "deadline_agent/.env could not be checked without python-dotenv", f"{RUN_SETUP} again, {USE_VENV}."
    except (OSError, ValueError):  # no permission, or not saved as plain text
        return False, "deadline_agent/.env could not be read", f"{RUN_SETUP} again to write a new one."
    if not key:
        return False, "deadline_agent/.env has no GOOGLE_API_KEY", f"{RUN_SETUP} again and paste your Gemini API key."
    if key == EXAMPLE_KEY:
        return (
            False,
            "GOOGLE_API_KEY in deadline_agent/.env is still the example text",
            f"{RUN_SETUP} again and paste your real Gemini API key.",
        )
    return True, "deadline_agent/.env has a GOOGLE_API_KEY (the key is not shown)", ""


def groot_is_running():
    """True if the program on port 8000 is adk web serving Groot.

    adk web answers /list-apps with the names of its agents, like ["deadline_agent"].
    The request goes straight to this computer, never through a proxy.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{PORT}/list-apps", timeout=5) as response:
            apps = json.loads(response.read())
    except (OSError, ValueError):  # not a web server, or its answer is not JSON
        return False
    return isinstance(apps, list) and "deadline_agent" in apps


def check_port():
    """Port 8000 is free for Groot, or Groot is already running on it."""
    try:
        # Nothing leaves this computer: 127.0.0.1 always means this computer itself
        with socket.create_connection(("127.0.0.1", PORT), timeout=5):
            pass
    except ConnectionRefusedError:
        return True, f"Port {PORT} is free", ""
    if groot_is_running():
        return True, f"Groot is already running at http://127.0.0.1:{PORT}", ""
    return (
        False,
        f"Another program is using port {PORT}",
        f"Close the program using port {PORT} (or restart your computer), then start Groot again.",
    )


def check_timezone():
    """Python can find the Australia/Sydney time zone, which every date in Groot uses.

    no_cache makes it really load the time zone, instead of reusing one loaded earlier.
    """
    import zoneinfo

    try:
        zoneinfo.ZoneInfo.no_cache("Australia/Sydney")
    except zoneinfo.ZoneInfoNotFoundError:
        return (
            False,
            "Python cannot find the Australia/Sydney time zone",
            f"{RUN_SETUP} again (it installs tzdata), {USE_VENV}.",
        )
    return True, "The Australia/Sydney time zone is available", ""


def check_deadlines_file():
    """The saved deadlines can be read, using the same code as Groot's tools. Nothing is changed."""
    import zoneinfo

    try:
        from . import tools  # tools.py loads the Sydney time zone as soon as it is imported
    except zoneinfo.ZoneInfoNotFoundError:
        return (
            False,
            "The deadlines file could not be checked without the Sydney time zone",
            "Fix the time zone problem above, then run this check again.",
        )
    path = tools._data_file()
    deadlines = tools._read_file(path)  # only reads: [] if there is no file, None if it cannot be understood
    if deadlines is None:
        return (
            False,
            f"{path} cannot be read or is not a valid list of deadlines",
            "Fix it by hand, or rename it so Groot starts a fresh list (see docs/reference.md, Where your deadlines are saved).",
        )
    if not path.exists():
        return True, f"No deadlines saved yet ({path.name} is made when you add your first one)", ""
    return True, f"{path} holds {tools._plural(len(deadlines), 'deadline')} and reads fine", ""


def check_gemini():
    """Sends one tiny real request to Gemini, with Groot's model, to prove the key works."""
    import httpx
    from google import genai
    from google.genai import errors, types

    from .agent import root_agent
    from .friendly_errors import friendly_message

    client = genai.Client(api_key=read_api_key(), http_options=types.HttpOptions(timeout=30_000))  # 30 seconds
    try:
        client.models.generate_content(model=root_agent.model, contents="Reply with just the word OK.")
    except errors.APIError as error:
        reason = friendly_message(error) or f"Gemini answered with an error: {error.code} {error.status}"
        return False, reason, "Follow the advice above, then run this check again with --online."
    except httpx.HTTPError as error:  # no internet, or no answer in 30 seconds
        return False, f"Could not reach Gemini ({type(error).__name__})", "Check your internet connection, then try again."
    return True, f"Gemini answered, so your key works ({root_agent.model})", ""


# ---------- running them ----------


def marks(stream):
    """The tick and the cross to print on stream: ✓ and ✗, or [OK] and [X] if its encoding cannot show them."""
    try:
        (TICK + CROSS).encode(stream.encoding)
    except (UnicodeEncodeError, LookupError):  # LookupError: an encoding Python does not know
        return PLAIN_TICK, PLAIN_CROSS
    return TICK, CROSS


def show(result):
    """Print one result, with its fix under a cross. Returns True if it passed."""
    passed, found, fix = result
    tick, cross = marks(sys.stdout)
    print(f"{tick if passed else cross} {found}")
    if not passed:
        print(f"    Fix: {fix}")
    return passed


def main(argv=None):
    """Run every check and return the exit code: 0 if all passed, 1 otherwise."""
    parser = argparse.ArgumentParser(description="Check that Agent Groot is set up.")
    parser.add_argument(
        "--online",
        action="store_true",
        help="also send one tiny real request to Gemini to prove your key works (uses 1 free request)",
    )
    args = parser.parse_args(argv)
    # Any other character the output cannot show, like a letter in a folder name, becomes "?" instead of crashing
    sys.stdout.reconfigure(errors="replace")

    print("Checking Agent Groot's setup...\n")
    if not show(check_python()):
        print("\nFix this first, then run this check again.")
        return 1

    checks = [check_packages, check_api_key, check_port, check_timezone, check_deadlines_file]
    passed = [show(check()) for check in checks]
    if args.online:
        if all(passed):
            print("\nNow sending one real request to Gemini. This uses 1 of your 20 free requests for today.")
            passed.append(show(check_gemini()))
        else:
            print("\nThe Gemini check was skipped, so no free request was used. Fix the problems above first.")
            passed.append(False)

    problems = passed.count(False)
    if problems == 0:
        print("\nAll good! Start Groot with start_groot.bat (Windows) or ./start_groot.sh (Linux and macOS).")
        return 0
    print(f"\n{problems} {'problem' if problems == 1 else 'problems'} found. Follow each Fix above, then run this check again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
