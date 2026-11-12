r"""Measure how well the outline reader finds the deadlines in real UTS outlines.

Run it from the project folder:

    .venv/bin/python -m eval.run_eval            (Linux and macOS)
    .\.venv\Scripts\python.exe -m eval.run_eval  (Windows)

Add --session AUT2026 for Autumn outlines. Spring 2026 (SPR2026) is the default.

It reads every checked answer key in eval/answer_key/, sends the outline with
the same subject code from eval/outlines/ (for example 33130.pdf or
33130.docx) to Gemini through extract_items, compares the two, and writes the
scores to eval/results.md. Timing is scored twice: by the timing fields, and
by the real dates the drop box would show, worked out for the session by the
same importer and UTS calendar. eval/README.md explains the answer key format
and how every score works.

Gemini's free tier only allows a few requests a minute, so this waits between
outlines and never sends more than 4 requests in any minute.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from time import monotonic, sleep

from deadline_agent import documents, importer, outline, tools, uts_calendar

EVAL_DIR = Path(__file__).resolve().parent
OUTLINES_DIR = EVAL_DIR / "outlines"
KEYS_DIR = EVAL_DIR / "answer_key"
RESULTS_FILE = EVAL_DIR / "results.md"

# The made-up key that shows the format. It is never scored.
EXAMPLE_KEY = "EXAMPLE.json"

# Real dates are worked out for this session, unless --session gives another.
DEFAULT_SESSION = "SPR2026"

# The importer's clock is frozen at Monday 20 Jul 2026, the week before Spring 2026 starts, as the
# spec says. The clock only decides which rows count as past, never a row's date, so no score
# depends on the day the measurement is run.
FROZEN_NOW = datetime(2026, 7, 20, 9, 0)

# At most 4 requests a minute: 60 / 4 = 15 seconds apart, plus 1 spare second for network delays.
# extract_items sends exactly one request per outline, so one outline is one request.
REQUESTS_PER_MINUTE = 4
SECONDS_BETWEEN_REQUESTS = 60 / REQUESTS_PER_MINUTE + 1

# Two names can be paired when they are at least this alike (0 to 1), as in the spec's Canvas matching.
MATCH_THRESHOLD = 0.6

# Two weights are the same when they are at most this far apart, so 3.33 equals 3.333.
WEIGHT_TOLERANCE = 0.05

# The fields that say when an item happens. Two timings are the same only if all of these are.
TIMING_FIELDS = ["when", "date", "week", "first_week", "last_week", "weekday", "time"]

# The fields an answer key may have. In each item, the timing fields left out count as null.
KEY_FIELDS = {"subject", "checked", "items"}
KEY_ITEM_REQUIRED = {"name", "weight_percent", "when"}
KEY_ITEM_FIELDS = KEY_ITEM_REQUIRED | set(TIMING_FIELDS) | {"note"}

# The field each kind of timing needs before the app can give it a date (spec's rules table).
# A tutorial with no week, the exam period and unknown never get a date.
DATE_FIELD = {"date": "date", "week": "week", "tutorial": "week", "recurring": "first_week"}


class EvalError(Exception):
    """A problem with an answer key or an outline file. The message says how to fix it."""


# ---------- answer keys ----------


def load_key(path: Path) -> dict:
    """Read one answer key and check it. Returns {"checked": True or False, "items": [...]}.

    Each item goes through the same checks as Gemini's answers, so a typo
    (like "Friday" instead of "friday") stops the run instead of quietly
    spoiling the scores.
    """
    try:
        key = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EvalError(f"{path.name} is not valid JSON: {error}") from error
    if not isinstance(key, dict) or set(key) != KEY_FIELDS:
        raise EvalError(f"{path.name} must have exactly these fields: checked, items, subject.")
    if not isinstance(key["checked"], bool):
        raise EvalError(f'{path.name}: "checked" must be true or false.')
    if not isinstance(key["items"], list):
        raise EvalError(f'{path.name}: "items" must be a list.')

    items = []
    for number, raw in enumerate(key["items"], start=1):
        where = f"{path.name} item {number}"
        if not isinstance(raw, dict):
            raise EvalError(f"{where} is not an object.")
        missing = KEY_ITEM_REQUIRED - set(raw)
        if missing:
            raise EvalError(f"{where} is missing {', '.join(sorted(missing))}.")
        unknown = set(raw) - KEY_ITEM_FIELDS
        if unknown:
            raise EvalError(f"{where} has unknown fields: {', '.join(sorted(unknown))}. Check the spelling in eval/README.md.")
        try:
            checked = outline.check_item(raw, "00000", "")
        except outline.OutlineError as error:
            raise EvalError(f"{where} needs a name.") from error
        # "when" goes last, so a bad date is reported as the date and not as its "when"
        for field in ["name", "weight_percent", "date", "week", "first_week", "last_week", "weekday", "time", "when"]:
            if checked[field] != raw.get(field):
                raise EvalError(f"{where}: {field} {raw.get(field)!r} does not follow the rules in eval/README.md.")
        items.append({field: checked[field] for field in ["name", "weight_percent", *TIMING_FIELDS]})
    return {"checked": key["checked"], "items": items}


def load_keys(keys_dir: Path) -> tuple[dict, list]:
    """Read every answer key. Returns ({code: items} for checked keys, [codes] of keys not checked yet)."""
    checked, unchecked = {}, []
    for path in sorted(keys_dir.glob("*.json")):
        if path.name == EXAMPLE_KEY:
            continue
        if not re.fullmatch(r"[0-9]{5}", path.stem):
            raise EvalError(f"{path.name}: an answer key must be named after its five-digit subject code, like 33130.json.")
        key = load_key(path)
        if key["checked"]:
            checked[path.stem] = key["items"]
        else:
            unchecked.append(path.stem)
    return checked, unchecked


# ---------- reading the outlines ----------


def find_outline(code: str, outlines_dir: Path) -> Path:
    """The one outline file for this subject code, for example 33130.pdf or 33130.docx."""
    matches = [
        path
        for path in sorted(outlines_dir.glob(f"{code}.*"))
        if path.is_file() and path.stem == code and path.suffix.lower() in documents.SUPPORTED_EXTENSIONS
    ]
    if not matches:
        raise EvalError(f"There is no outline for {code}. Put it in {outlines_dir}, named like {code}.pdf or {code}.docx")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise EvalError(f"There is more than one outline for {code} ({names}). Keep only one of them in {outlines_dir}")
    return matches[0]


def read_outlines(codes: list, outlines_dir: Path, client=None) -> dict:
    """Run extract_items on each outline file, waiting so there are at most 4 requests a minute.

    Returns {code: extracted items}. Any OutlineError stops the whole run.
    """
    # Find every outline first, so a missing file does not waste requests
    paths = {code: find_outline(code, outlines_dir) for code in codes}

    found = {}
    last_start = None
    for code, path in paths.items():
        if last_start is not None:
            wait = SECONDS_BETWEEN_REQUESTS - (monotonic() - last_start)
            if wait > 0:
                print(f"  Waiting {wait:.0f} seconds to stay under {REQUESTS_PER_MINUTE} requests a minute...")
                sleep(wait)
        last_start = monotonic()
        print(f"Reading {path.name} with {outline.MODEL}...")
        found[code] = outline.extract_items(path.read_bytes(), filename=path.name, client=client)
    return found


# ---------- pairing key items with extracted items ----------


def normalise(name: str) -> str:
    """Lower case, with each run of punctuation and spaces turned into one space."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def name_similarity(key_name: str, found_name: str) -> float:
    """How alike two names are, from 0 (nothing alike) to 1 (the same after normalising).

    Every number in the key's name must also be in the found name, otherwise
    it is 0. So "Skills Test 2" is never paired with "Skills Test 7".
    """
    key_name, found_name = normalise(key_name), normalise(found_name)
    if not set(re.findall(r"[0-9]+", key_name)) <= set(re.findall(r"[0-9]+", found_name)):
        return 0.0
    return SequenceMatcher(None, key_name, found_name).ratio()


def match_items(key_items: list, found_items: list) -> list[tuple[int, int]]:
    """Pair each key item with at most one extracted item, best pairs first.

    Returns (key position, found position) pairs, sorted by key position.
    Pairs below MATCH_THRESHOLD are never made. When two pairs are equally
    alike, the one that comes first in the key wins, then the one that comes
    first in Gemini's answer, so the result is the same every run.
    """
    candidates = []
    for k, key_item in enumerate(key_items):
        for f, found_item in enumerate(found_items):
            score = name_similarity(key_item["name"], found_item["name"])
            if score >= MATCH_THRESHOLD:
                candidates.append((-score, k, f))  # minus, so the most alike sorts first

    pairs = []
    used_keys, used_found = set(), set()
    for _, k, f in sorted(candidates):
        if k not in used_keys and f not in used_found:
            pairs.append((k, f))
            used_keys.add(k)
            used_found.add(f)
    return sorted(pairs)


# ---------- scores ----------


def gives_a_date(item: dict) -> bool:
    """True if the app would show this item with a date (status exact or assumed)."""
    field = DATE_FIELD.get(item["when"])
    return field is not None and item[field] is not None


def same_timing(key_item: dict, found_item: dict) -> bool:
    """True if every timing field is the same, so the calendar would turn both into the same day."""
    return all(key_item[field] == found_item[field] for field in TIMING_FIELDS)


def same_weight(key_weight, found_weight) -> bool:
    """True if both weights are missing, or they are within WEIGHT_TOLERANCE of each other."""
    if key_weight is None or found_weight is None:
        return key_weight is None and found_weight is None
    return abs(key_weight - found_weight) <= WEIGHT_TOLERANCE


def describe_timing(item: dict) -> str:
    """The timing fields that are set, for example "when=week, week=2"."""
    return ", ".join(f"{field}={item[field]}" for field in TIMING_FIELDS if item[field] is not None)


def resolve_dates(item: dict, code: str, session: str) -> tuple:
    """The due dates the drop box would show for this item, worked out by the real importer and UTS calendar.

    item is a key item or an extracted item. The result is one "YYYY-MM-DD HH:MM" for most items,
    one for each teaching week of a weekly item, and none when the drop box shows no date or asks
    the student for one. There is no timetable here, so a tutorial in week N gets no date either.
    """
    # A key item only has the fields that are scored, so the importer gets the rest of an ExtractedItem
    full_item = {"subject_code": code, "subject_name": "", "task_number": None, "quote": "", **item}
    rows = importer.build_preview([full_item], session, now=FROZEN_NOW)
    return tuple(row["due_date"] for row in rows if row["due_date"] is not None)


def describe_dates(dates: tuple) -> str:
    """For example "Friday 7 Aug 2026, 11:59 PM", "9 dates, Friday 21 Aug 2026, 11:59 PM to ..." or "no date"."""
    if not dates:
        return "no date"
    shown = [tools._friendly(tools._parse_due_date(due)) for due in dates]
    if len(shown) == 1:
        return shown[0]
    return f"{len(shown)} dates, {shown[0]} to {shown[-1]}"


def score_outline(key_items: list, found_items: list, code: str, session: str) -> dict:
    """Compare one outline's answer key with what was extracted. Returns counts and the mistakes.

    code is the outline's subject code, and session ("SPR2026" or "AUT2026") gives the calendar
    the real dates are worked out with.
    """
    pairs = match_items(key_items, found_items)
    paired_keys = {k for k, _ in pairs}
    paired_found = {f for _, f in pairs}
    score = {
        "key_items": len(key_items),
        "found_items": len(found_items),
        "matched": len(pairs),
        "weights_right": 0,
        "timed": 0,  # paired items whose key gives a date, by the timing fields
        "timing_right": 0,
        "dated": 0,  # paired items whose key resolves to a real date
        "dates_right": 0,
        "silently_wrong": 0,
        "missed": [item["name"] for k, item in enumerate(key_items) if k not in paired_keys],
        "invented": [item["name"] for f, item in enumerate(found_items) if f not in paired_found],
        "wrong_weights": [],
        "wrong_timings": [],
        "wrong_dates": [],
    }
    for k, f in pairs:
        key_item, found_item = key_items[k], found_items[f]
        if same_weight(key_item["weight_percent"], found_item["weight_percent"]):
            score["weights_right"] += 1
        else:
            score["wrong_weights"].append(
                f'"{key_item["name"]}": key {key_item["weight_percent"]}, found {found_item["weight_percent"]}'
            )

        right = same_timing(key_item, found_item)
        if gives_a_date(key_item):
            score["timed"] += 1
            if right:
                score["timing_right"] += 1
        if not right:
            # If the wrong timing still gives a date, the student sees it with no warning
            silent = gives_a_date(found_item)
            if silent:
                score["silently_wrong"] += 1
            score["wrong_timings"].append(
                f'"{key_item["name"]}": key {describe_timing(key_item)}, found {describe_timing(found_item)}'
                + (" (silently wrong)" if silent else "")
            )

        key_dates = resolve_dates(key_item, code, session)
        if key_dates:
            score["dated"] += 1
            found_dates = resolve_dates(found_item, code, session)
            if found_dates == key_dates:
                score["dates_right"] += 1
            else:
                score["wrong_dates"].append(
                    f'"{key_item["name"]}": key {describe_dates(key_dates)}, found {describe_dates(found_dates)}'
                )
    return score


# ---------- results.md ----------

COUNTS = [
    "key_items", "found_items", "matched", "weights_right", "timed", "timing_right", "dated", "dates_right",
    "silently_wrong",
]


def fraction(part: int, whole: int) -> str:
    """For example "9 of 10 (90%)". With nothing to count it is just "0 of 0"."""
    if whole == 0:
        return "0 of 0"
    return f"{part} of {whole} ({part / whole:.0%})"


def table_row(label: str, score: dict) -> str:
    """One row of the results table."""
    cells = [
        label,
        fraction(score["matched"], score["key_items"]),
        fraction(score["matched"], score["found_items"]),
        fraction(score["weights_right"], score["matched"]),
        fraction(score["timing_right"], score["timed"]),
        fraction(score["dates_right"], score["dated"]),
        str(score["silently_wrong"]),
    ]
    return "| " + " | ".join(cells) + " |"


def render(scores: dict, unchecked: list, session: str) -> str:
    """The whole results.md file."""
    total = {name: sum(score[name] for score in scores.values()) for name in COUNTS}
    calendar = uts_calendar.session_info(session)["name"]
    lines = [
        "# Outline reader accuracy",
        "",
        f"Made by `eval/run_eval.py` with {outline.MODEL} on {len(scores)} outline(s). Real dates are worked out"
        f" for {calendar} ({session}) with the clock frozen at {tools._friendly_day(FROZEN_NOW)}."
        " eval/README.md explains how each score is worked out.",
        "",
        "| Outline | Items found (recall) | Items not invented (precision) | Weights correct | Timing correct"
        " | Dates correct | Silently wrong dates |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [table_row(code, score) for code, score in scores.items()]
    lines.append(table_row("All", total))

    for code, score in scores.items():
        lines += ["", f"## {code}", ""]
        for title, mistakes in [
            ("Missed", score["missed"]),
            ("Invented", score["invented"]),
            ("Wrong weight", score["wrong_weights"]),
            ("Wrong timing", score["wrong_timings"]),
            ("Wrong date", score["wrong_dates"]),
        ]:
            if not mistakes:
                lines.append(f"- {title}: none")
            else:
                lines.append(f"- {title}:")
                lines += [f"  - {mistake}" for mistake in mistakes]  # one mistake per line

    if unchecked:
        lines += ["", "Not counted, because the answer key is not checked yet: " + ", ".join(unchecked) + "."]
    return "\n".join(lines) + "\n"


# ---------- running it ----------


def evaluate(outlines_dir: Path, keys_dir: Path, session: str, client=None) -> str:
    """Score every checked answer key against its outline and return the text of results.md.

    session ("SPR2026" or "AUT2026") is checked first, so a typo never wastes a Gemini request.
    """
    try:
        uts_calendar.session_info(session)
    except ValueError as error:
        raise EvalError(str(error)) from None
    keys, unchecked = load_keys(keys_dir)
    for code in unchecked:
        print(f"Skipping {code}: its answer key is not checked yet.")
    if not keys:
        raise EvalError('There are no checked answer keys yet. Set "checked": true in a key once you have checked it.')
    found = read_outlines(list(keys), outlines_dir, client)
    scores = {code: score_outline(keys[code], found[code], code, session) for code in keys}
    return render(scores, unchecked, session)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Measure how well the outline reader finds the deadlines in UTS outlines.")
    parser.add_argument(
        "--session",
        choices=list(uts_calendar.SESSIONS),
        default=DEFAULT_SESSION,
        help=f"the session of the outlines, whose calendar gives the real dates (default {DEFAULT_SESSION})",
    )
    args = parser.parse_args(argv)
    print(
        f"Gemini's free tier allows only a few requests a minute, so this sends at most {REQUESTS_PER_MINUTE}"
        f" a minute ({SECONDS_BETWEEN_REQUESTS:.0f} seconds apart)."
    )
    try:
        results = evaluate(OUTLINES_DIR, KEYS_DIR, args.session)
    except (EvalError, outline.OutlineError) as error:
        sys.exit(f"Stopped. eval/results.md was not changed.\n{error}")
    RESULTS_FILE.write_text(results, encoding="utf-8", newline="\n")
    print()
    print(results)
    print(f"Saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
