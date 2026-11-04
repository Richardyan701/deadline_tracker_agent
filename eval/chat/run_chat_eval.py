"""Chat evaluation for Agent Groot: how well does the real Gemini model use Groot's tools?

Every case in cases.jsonl is one student message. For each case this script
starts a fresh chat with the real root_agent, gives it its own temporary
deadlines file and a frozen clock, sends the message and records every tool
call, what each tool gave back and Groot's final reply. Then it scores the
case by looking at the tool calls and the saved deadlines file, never at the
model's wording.

Run it from the project folder (see eval/chat/README.md for more):

    python -m eval.chat.run_chat_eval             every case
    python -m eval.chat.run_chat_eval --limit 5   only the first 5 cases
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.runners import InMemoryRunner
from google.genai import errors, types

from deadline_agent import tools
from deadline_agent.agent import root_agent

HERE = Path(__file__).resolve().parent
CASES_FILE = HERE / "cases.jsonl"
RUNS_DIR = HERE / "runs"  # one saved result per case, so a stopped run can carry on
RESULTS_FILE = HERE / "results.md"
KEY_FILE = HERE.parent.parent / "deadline_agent" / ".env"  # the same key file adk web uses

# Tools that only look at the deadlines. Calling one of these as well as the
# expected tool is fine, for example listing first to check a title.
READ_ONLY_TOOLS = {"list_deadlines", "next_deadline", "get_reminders"}

# Every check, with the words used for it in results.md
CHECKS = {
    "right_tool": "Right tool chosen",
    "no_tool": "No tool call for an off-topic message",
    "date_as_typed": "Due date passed exactly as typed",
    "saved_correctly": "Saved deadlines correct",
    "nothing_changed": "Nothing saved that should not be",
}


def load_cases(path: Path) -> list:
    """Read the cases, one JSON object per line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class Throttle(BasePlugin):
    """Waits before each request to Gemini, so no more than per_minute are sent in a minute.

    ADK calls before_model_callback just before every request to the model,
    so this counts real requests, including the second request after a tool runs.
    """

    def __init__(self, per_minute: int):
        super().__init__(name="throttle")
        self.gap = 60 / per_minute  # seconds to leave between two requests
        self.last_request = None  # when the last request was sent
        # The tests swap these two for fakes, so they never really wait
        self.clock = time.monotonic
        self.sleep = asyncio.sleep

    async def before_model_callback(self, *, callback_context, llm_request):
        if self.last_request is not None:
            wait = self.last_request + self.gap - self.clock()
            if wait > 0:
                await self.sleep(wait)
        self.last_request = self.clock()
        return None  # None means "send the request as normal"


# ---------- running one case ----------


async def run_case(runner: InMemoryRunner, case: dict) -> dict:
    """Send one case's message to Groot in a fresh chat and record what happened."""
    now = datetime.strptime(case["now"], "%Y-%m-%d %H:%M")
    calls, results, replies, versions, errors = [], {}, [], set(), []

    with tempfile.TemporaryDirectory() as folder:
        deadlines_file = Path(folder) / "deadlines.json"
        deadlines_file.write_text(json.dumps(case.get("seed", []), indent=2), encoding="utf-8")

        # Point Groot at the temporary file and freeze its clock, for this case only.
        # Both are put back as they were when the "with" block ends.
        use_temporary_file = patch.dict(os.environ, {"DEADLINES_FILE": str(deadlines_file)})
        freeze_clock = patch.object(tools, "_now", lambda: now)
        with use_temporary_file, freeze_clock:
            session = await runner.session_service.create_session(app_name=runner.app_name, user_id="student")
            message = types.Content(role="user", parts=[types.Part.from_text(text=case["message"])])
            async for event in runner.run_async(user_id="student", session_id=session.id, new_message=message):
                calls += event.get_function_calls()
                for response in event.get_function_responses():
                    results[response.id] = response.response
                if event.is_final_response() and event.content and event.content.parts:
                    # Skip the model's hidden thinking, keep only what the student would see
                    replies += [part.text for part in event.content.parts if part.text and not part.thought]
                if event.model_version:
                    versions.add(event.model_version)
                if event.error_code:  # Gemini sent no answer and said why, for example SAFETY
                    errors.append(f"{event.error_code}: {event.error_message}")

        saved = json.loads(deadlines_file.read_text(encoding="utf-8"))

    return {
        "case": case,
        # ADK gives every call an id, and the tool's result comes back with the same id
        "calls": [{"tool": call.name, "args": dict(call.args or {}), "result": results[call.id]} for call in calls],
        "reply": "\n".join(replies),
        "saved": saved,
        "model_versions": sorted(versions),
        "model_errors": errors,
    }


async def run_all(cases: list, agent, runs_dir: Path, plugins=()) -> list:
    """Run every case and return their records.

    A case already saved in runs_dir from an earlier run is reused, as long as
    the case itself has not changed since. If anything goes wrong in a case (for
    example Gemini answers 429 RESOURCE_EXHAUSTED), the run stops there, and
    running it again carries on from that case.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    runner = InMemoryRunner(app=App(name="groot_eval", root_agent=agent, plugins=list(plugins)))
    records = []
    for number, case in enumerate(cases, start=1):
        run_file = runs_dir / f"{case['id']}.json"
        record = json.loads(run_file.read_text(encoding="utf-8")) if run_file.exists() else None
        if record is None or record["case"] != case:
            try:
                record = await run_case(runner, case)
            except Exception:
                print(f"Stopped at case {case['id']}.")
                raise
            run_file.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        failed = [CHECKS[name] for name, passed in score(case, record).items() if not passed]
        print(f"[{number}/{len(cases)}] {case['id']}: " + (f"FAILED ({', '.join(failed)})" if failed else "passed"))
        records.append(record)
    return records


# ---------- scoring ----------


def date_words(text) -> str:
    """The due date words the way add_deadline reads them.

    Upper/lower case, commas, extra spaces and the little words "due", "by",
    "on" and "at" make no difference to the tool, so they make none here either.
    """
    words = str(text).lower().replace(",", " ").split()
    return " ".join(word for word in words if word not in tools.FILLER_WORDS)


def same_deadlines(saved: list, expected: list) -> bool:
    """True if both lists hold the same deadlines, in any order.

    Titles and subjects are compared the way Groot compares titles, so upper
    and lower case and extra spaces are ignored. Due dates and done must match exactly.
    """
    def tidy(deadlines):
        return sorted(
            (tools._title_key(d["title"]), d["due_date"], tools._title_key(d["subject"]), d["done"])
            for d in deadlines
        )
    return tidy(saved) == tidy(expected)


def score(case: dict, record: dict) -> dict:
    """Which checks the case passed: {check name: True or False}. Only checks that apply are included."""
    expected_calls = case["expect"]["calls"]
    expected_tools = {call["tool"] for call in expected_calls}
    called_tools = {call["tool"] for call in record["calls"]}
    checks = {}

    if expected_tools:
        # Every expected tool was called, and any other tool only looked at the deadlines
        checks["right_tool"] = (expected_tools <= called_tools) and ((called_tools - expected_tools) <= READ_ONLY_TOOLS)
    else:
        # Off topic: no tool at all, and Groot still said something back
        checks["no_tool"] = not record["calls"] and bool(record["reply"].strip())

    typed = [call["args"]["due_date"] for call in expected_calls if call["tool"] == "add_deadline"]
    if typed:
        # Every add_deadline call (a retry too) must carry the student's own words, not a converted date
        sent = [call["args"].get("due_date") for call in record["calls"] if call["tool"] == "add_deadline"]
        checks["date_as_typed"] = bool(sent) and all(date_words(words) == date_words(typed[0]) for words in sent)

    seed = case.get("seed", [])
    if same_deadlines(case["expect"]["saved"], seed):
        checks["nothing_changed"] = same_deadlines(record["saved"], seed)
    else:
        checks["saved_correctly"] = same_deadlines(record["saved"], case["expect"]["saved"])
    return checks


# ---------- results.md ----------


def percent(passed: int, total: int) -> str:
    return f"{100 * passed / total:.0f}%" if total else "-"


def show_call(call: dict) -> str:
    """For example: add_deadline(title='Quiz 2', due_date='next friday 5pm')"""
    args = ", ".join(f"{name}={value!r}" for name, value in call["args"].items())
    return f"{call['tool']}({args})"


def show_deadlines(deadlines: list) -> list:
    """One markdown bullet per deadline."""
    if not deadlines:
        return ["- (none)"]
    lines = []
    for d in deadlines:
        subject = f"subject `{d['subject']}`" if d["subject"] else "no subject"
        lines.append(f"- `{d['title']}`, due `{d['due_date']}`, {subject}, {'done' if d['done'] else 'not done'}")
    return lines


def failed_case_lines(record: dict, checks: dict) -> list:
    """The details of one failed case for results.md."""
    case = record["case"]
    failed = [CHECKS[name] for name, passed in checks.items() if not passed]
    lines = [f"### {case['id']}", "", f"Category: {case['category']}. Failed: {', '.join(failed)}.", ""]
    lines += [f"Student (clock frozen at {case['now']}): `{case['message']}`", "", "Tool calls made:"]
    # A tool's result can be long (a whole list), so only the start is shown
    lines += [
        f"- `{show_call(call)}` gave `{json.dumps(call['result'], ensure_ascii=False)[:200]}`"
        for call in record["calls"]
    ] or ["- (none)"]
    lines += ["", "Tool calls expected:"]
    lines += [f"- `{show_call(call)}`" for call in case["expect"]["calls"]] or ["- (none)"]
    lines += ["", "Saved afterwards:"] + show_deadlines(record["saved"])
    lines += ["", "Expected saved:"] + show_deadlines(case["expect"]["saved"])
    lines += ["", "Groot replied:", ""] + [f"> {line}" for line in (record["reply"] or "(nothing)").splitlines()]
    if record["model_errors"]:
        lines += [""] + [f"Model error: `{error}`" for error in record["model_errors"]]
    return lines + [""]


def write_results(records: list, path: Path, total_cases: int) -> None:
    """Write results.md: the overall table, a table per category and every failed case."""
    scored = [(record, score(record["case"], record)) for record in records]
    passed_cases = [record for record, checks in scored if all(checks.values())]
    versions = sorted({version for record in records for version in record["model_versions"]})

    lines = ["# Chat evaluation results", ""]
    lines += [f"Model, as reported by Gemini: {', '.join(versions) or 'not reported'}.", ""]
    lines += [f"Cases scored: {len(records)} of {total_cases}."]
    if len(records) < total_cases:
        lines += ["This was a partial run (--limit), so these numbers do not cover every case."]
    lines += ["", "## Overall", "", "| Check | Passed | Out of | Score |", "| --- | --- | --- | --- |"]
    lines.append(f"| Whole cases (every check passed) | {len(passed_cases)} | {len(records)} | {percent(len(passed_cases), len(records))} |")
    for name, label in CHECKS.items():
        results = [checks[name] for _, checks in scored if name in checks]
        lines.append(f"| {label} | {sum(results)} | {len(results)} | {percent(sum(results), len(results))} |")

    lines += ["", "## By category", "", "| Category | Passed | Out of | Score |", "| --- | --- | --- | --- |"]
    categories = list(dict.fromkeys(record["case"]["category"] for record in records))  # in file order
    for category in categories:
        total = sum(record["case"]["category"] == category for record in records)
        passed = sum(record["case"]["category"] == category for record in passed_cases)
        lines.append(f"| {category} | {passed} | {total} | {percent(passed, total)} |")

    lines += ["", "## Failed cases", ""]
    failed = [(record, checks) for record, checks in scored if not all(checks.values())]
    for record, checks in failed:
        lines += failed_case_lines(record, checks)
    if not failed:
        lines += ["None.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- the command ----------


def at_least_one(text: str) -> int:
    """For argparse: a whole number that is 1 or more."""
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def evaluation_agent():
    """Groot exactly as students get it, except that Gemini errors are not turned into friendly replies.

    In normal use a limit error becomes a polite message (deadline_agent/friendly_errors.py). Here that
    message would be scored as if it were Groot's real answer, so the error must reach run_all instead,
    which stops the run without saving the case, and the next run carries on from there.
    """
    return root_agent.model_copy(update={"on_model_error_callback": None})


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Score how well the real Gemini model uses Groot's tools.")
    parser.add_argument("--limit", type=at_least_one, help="only run the first N cases, for a quick check")
    parser.add_argument("--per-minute", type=at_least_one, default=4,
                        help="the most requests to send to Gemini in a minute (default 4, for the free tier)")
    args = parser.parse_args(argv)

    load_dotenv(KEY_FILE)  # a key already set in the environment wins over the file
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        sys.exit(f"No Gemini API key found. Run the setup script to save your key in {KEY_FILE}, then try again.")

    all_cases = load_cases(CASES_FILE)
    cases = all_cases[: args.limit]  # [:None] keeps every case
    try:
        records = asyncio.run(run_all(cases, evaluation_agent(), RUNS_DIR, plugins=[Throttle(args.per_minute)]))
    except errors.APIError as error:
        # Gemini refused the request. ADK has already printed the full details above,
        # so end with a short note. Any other error is a bug and shows its whole traceback.
        sys.exit(f"\nA request to Gemini failed: {error}\n"
                 f"Finished cases are saved in {RUNS_DIR}, so run the same command again later to carry on.")
    write_results(records, RESULTS_FILE, total_cases=len(all_cases))
    print(f"Wrote {RESULTS_FILE}")


if __name__ == "__main__":
    main()
