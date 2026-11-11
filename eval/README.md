# Measuring the outline reader

This folder checks how well the outline reader (`deadline_agent/outline.py`) finds the deadlines in real UTS subject outlines. You write down the right answers for each outline once (the answer key), then `run_eval.py` sends each outline to Gemini, compares Gemini's items with your key, and writes the scores to `results.md`.

## What is in here

| Path | What it is | In git? |
| --- | --- | --- |
| `run_eval.py` | The script that runs the measurement | Yes |
| `answer_key/<code>.json` | The right answers for one outline, for example `answer_key/33130.json` | Yes |
| `answer_key/EXAMPLE.json` | A made up key that shows the format. It is never scored | Yes |
| `outlines/<code>.<ending>` | The outline files, for example `outlines/33130.pdf` or `outlines/35010.docx` | No. They are UTS documents, so `eval/.gitignore` keeps them off GitHub |
| `results.md` | The scores from the last run | Yes, once you have run it |

## How to run it

1. Run the setup script once if you have not already (`./setup.sh` on Linux and macOS, `setup_windows.bat` on Windows). It creates `.venv` and saves your Gemini key in `deadline_agent/.env`. The measurement uses that same key.
2. Make a folder called `outlines` inside `eval`, and copy each outline into it, named after its subject code: `eval/outlines/33130.pdf`, `eval/outlines/35010.pdf` and so on. An outline can be any kind of file the reader understands (see "Supported file types" in [docs/reference.md](../docs/reference.md#supported-file-types)), for example `eval/outlines/31250.docx`. Keep only one file for each subject code, or the script stops and asks you to remove the others.
3. Make sure each outline has an answer key with the same code, for example `eval/answer_key/33130.json`, and that you have checked it and set `"checked": true` (see below).
4. From the project folder, run:

   Linux and macOS:

   ```
   .venv/bin/python -m eval.run_eval
   ```

   Windows:

   ```
   .\.venv\Scripts\python.exe -m eval.run_eval
   ```

5. Open `eval/results.md` to see the scores, and the list of mistakes under each outline.

It must be started with `-m eval.run_eval` from the project folder (not `python eval/run_eval.py`), so Python can find the `deadline_agent` folder.

Real dates are worked out with the Spring 2026 calendar unless you say otherwise. For Autumn 2026 outlines, add `--session AUT2026`, for example `.venv/bin/python -m eval.run_eval --session AUT2026`. Every outline in one run is scored with the same session's calendar, so keep the checked answer keys in `eval/answer_key/` to one session for a run. Each run replaces `results.md`, so copy it somewhere first if you want to keep it. A session the calendar does not know is refused before anything is sent to Gemini.

### The free tier limit

Gemini's free tier only allows a few requests per minute. The script sends one request per outline and waits so that requests start at least 16 seconds apart, which keeps it at no more than 4 requests in any minute (15 seconds would be exactly 4, and the extra second allows for network delays). It prints a line each time it waits. With four outlines the requests start at about 0, 16, 32 and 48 seconds, plus however long Gemini takes to read each one.

### When it stops

If anything goes wrong (a missing outline, a file the reader cannot open, a typo in a key, a wrong API key, Gemini being busy or too slow, or an answer that cannot be read), the script stops, says why, and leaves `results.md` as it was. It never writes scores for only some of the outlines. Fix the problem and run it again.

## The answer key format

Each key is a JSON file named after the subject code. Here is a short one:

```json
{
  "subject": "99999 Example Subject",
  "checked": true,
  "items": [
    {"name": "Skills Test 1", "weight_percent": 10, "when": "week", "week": 2, "note": "page 3"},
    {"name": "Skills Test 2", "weight_percent": 10, "when": "tutorial"},
    {"name": "Weekly quizzes", "weight_percent": 20, "when": "recurring", "first_week": 4},
    {"name": "Assignment 1", "weight_percent": 30, "when": "date", "date": "2026-09-04", "weekday": "friday", "time": "23:59"},
    {"name": "Final exam", "weight_percent": 30, "when": "exam_period"}
  ]
}
```

`answer_key/EXAMPLE.json` is a full example with every kind of timing.

The file has exactly three fields:

| Field | Meaning |
| --- | --- |
| `subject` | The subject code and name, for people reading the file. It is not scored. |
| `checked` | `false` while the key is a draft. Set it to `true` only after you have compared every item with the outline yourself. Keys that are not checked are skipped and listed at the bottom of `results.md`. |
| `items` | Every separately dated assessment item in the outline, in any order. |

Each item has these fields. The first three are required. The timing fields you leave out count as `null`.

| Field | Meaning |
| --- | --- |
| `name` | The outline's own name for the item. Split items get a number, for example six items `"Skills Test 1"` to `"Skills Test 6"`. |
| `weight_percent` | This item's share of the final mark, for example `10` for one of six tests in a 60% task, or `null` if the outline gives no weight. A weekly series gets the weight of the whole series. |
| `when` | One of `date`, `week`, `tutorial`, `recurring`, `exam_period`, `unknown` (meanings below). |
| `date` | `"YYYY-MM-DD"`, only if the outline gives a calendar date. |
| `week` | The teaching week number, only if the outline gives one. |
| `first_week`, `last_week` | The first and last week of a weekly series. If the outline gives no last week, leave `last_week` out. |
| `weekday` | `"monday"` to `"sunday"` in lower case, only if the outline names the day. |
| `time` | `"HH:MM"` in 24 hour time, only if the outline names a time. 11:59 PM is `"23:59"`. |
| `note` | Optional. Anything that helps you check the item later, like the page or the outline's words. It is not scored. |

How to choose `when` (take the first one that fits):

| `when` | Use it when the outline... | Example wording |
| --- | --- | --- |
| `date` | gives a calendar date | "Due Friday 4 September 2026 at 11:59pm" |
| `recurring` | says it happens every week | "Each week starting from week 4" |
| `tutorial` | says it is held in a tutorial, workshop or class | "held during the tutorial classes", "held in the final tutorial (week 12)" |
| `week` | gives a teaching week | "is due in week 2" |
| `exam_period` | says it is an exam in the exam period | "a centrally-conducted restricted open book exam" |
| `unknown` | gives no timing at all | Only the task and its weight, or "see Canvas" |

The key copies the outline exactly, like the reader is asked to. Never work out a date from a week, and never add a day or time the outline does not state. Words about what an item covers are not timing: "assesses the final two weeks" does not mean it happens in those weeks.

Each key item goes through the same checks as Gemini's answers. If one of its values would be changed by those checks (for example `"Friday"` instead of `"friday"`, a week with no number, or a misspelled field like `"weeks"`), the run stops and names the item and the field, so a typo can never quietly spoil the scores.

## How items are paired

Gemini's names rarely match the key letter for letter, so each key item is paired with at most one of Gemini's items by name. The pairing is the same every time you run it on the same answer:

1. Both names are put in lower case, and each run of spaces and punctuation becomes one space. "Skills-Test #1 (Online)" becomes "skills test 1 online".
2. Every number in the key's name must also be in Gemini's name, otherwise the two can never be paired. This stops "Skills Test 2" being paired with "Skills Test 7".
3. How alike the two names are is measured with Python's `difflib.SequenceMatcher(...).ratio()`. It is 2 times the number of matching letters, divided by the total length of both names, so it runs from 0 (nothing alike) to 1 (the same). For example "skills test 6" against "skills test 6 weeks 11 12" is 2 × 13 / (13 + 25) = 0.68.
4. Pairs below 0.6 are never made. This is the same limit the spec uses for matching Canvas events.
5. All the possible pairs are sorted from most alike to least alike, and taken in that order, skipping any item that is already paired. When two pairs are exactly as alike, the one that comes first in the key wins, then the one that comes first in Gemini's answer.

A key item with no pair was **missed**. One of Gemini's items with no pair was **invented**.

## How each score is worked out

The scores are worked out for each outline, and then for all outlines together by adding up the counts first.

| Score | Worked out as |
| --- | --- |
| Items found (recall) | Paired items ÷ items in the key |
| Items not invented (precision) | Paired items ÷ items Gemini found |
| Weights correct | Paired items whose weights agree ÷ paired items. Weights agree when both are `null`, or when they are at most 0.05 apart, so 3.33 and 3.333 agree. |
| Timing correct | Paired items whose timing is right ÷ paired items where the key gives a date |
| Dates correct | Paired items whose real dates agree ÷ paired items where the key has a real date |
| Silently wrong dates | Paired items whose timing is wrong but would still be shown with a date. The target is 0. |

Some words used above:

- **Timing is right** when all seven timing fields (`when`, `date`, `week`, `first_week`, `last_week`, `weekday`, `time`) are exactly the same as the key. Two items with the same seven fields always turn into the same day in the calendar.
- **Gives a date** follows the spec's rules table: `date` with a date, `week` with a week, `tutorial` with a week (with a timetable it gets an exact day), and `recurring` with a first week. A tutorial with no week, `exam_period` and `unknown` are shown with no date, so the student is told to check them and they can never be silently wrong.
- **Real dates** are the dates the drop box would show. The key item and Gemini's item each go through the same importer (`deadline_agent/importer.py`) and UTS calendar (`deadline_agent/uts_calendar.py`) as the web page, for the session you chose. Most items get one date, a weekly item gets one date for each teaching week (StuVac is skipped), and an item the drop box shows without a date gets none. The real dates agree only when the two lists are exactly the same, to the minute.
- **Silently wrong** means the app would show the student a wrong date as if it were fine. For example the key says "tutorial, no week" but Gemini said "week 5", or the key says week 2 and Gemini said week 3.

Timing and dates are scored side by side because they catch different things. Comparing all seven fields is stricter: if the key says week 7 and Gemini says week 7 and Friday, the timing is wrong, because Gemini added a day the outline does not state, but both land on the same Friday, so the date is right. The other way round never happens, because the same timing always gives the same dates. The importer's clock is frozen at Monday 20 Jul 2026, the week before Spring 2026 starts. The clock only decides which rows count as past, never a row's date, so no score depends on the day you run it.

Under each outline, `results.md` lists every **Wrong date** too, for example `"Report": key Friday 18 Sep 2026, 11:59 PM, found Friday 2 Oct 2026, 11:59 PM`. A weekly item is shown as how many dates it has and where they start and end.

### What this does not measure

- **One session for each run.** An answer key does not say which session its outline is for, so every outline in a run gets the calendar of the session you chose.
- **A tutorial in a given week has no real date here.** The drop box needs your timetable to know the day of your tutorial, and the measurement has no timetable, so these items count under "Timing correct" but not under "Dates correct".
- **Silently wrong dates are counted by the timing fields**, so an added weekday that lands on the right day still counts. This keeps the strict count the spec asks for.
- **Silently wrong dates only counts paired items.** A made up item is counted under precision instead.
- **One run is one sample.** Gemini can answer a little differently each time, so small changes between runs are normal.
