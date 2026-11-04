# Agent Groot: a study deadline assistant

[![Tests](https://github.com/Richardyan701/deadline_tracker_agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Richardyan701/deadline_tracker_agent/actions/workflows/tests.yml)

Agent Groot is a chat assistant that keeps track of university assignment and exam deadlines. You tell it about a deadline in your own words, like "Quiz 2 due next friday 5pm", and it saves it to a file on your computer. It can list your deadlines, find the next one, mark them done or delete them. When you start a chat, it mentions anything overdue or due in the next 7 days. It runs on Google's Agent Development Kit (ADK) with the Gemini 3.5 Flash model, and the date maths is done in plain Python code instead of by the model, so a date like "next friday" always follows the same rules. It was built by Richard, a first year artificial intelligence student at UTS in Sydney.

## Quick start

1. **Run the setup script once.** On Windows, double click `setup_windows.bat`. On Linux or macOS, run `./setup.sh`. It installs everything and asks for your free Gemini API key. [Setup](#setup) says what you need first.
2. **Start Groot.** On Windows, double click `start_groot.bat`. On Linux or macOS, run `./start_groot.sh`.
3. **Chat in the browser tab that opens.** Say hello and Groot suggests a few things to try. If a box asks about sharing usage data with Google, either button is fine. Press Ctrl+C in the start window to stop Groot.

If anything goes wrong, run the setup checker (`.venv\Scripts\python.exe -m deadline_agent.check_setup` on Windows, `.venv/bin/python -m deadline_agent.check_setup` on Linux and macOS) and follow the fix it gives under each cross.

## What it can do

Groot has seven tools. Gemini reads what you type and decides which tool to call.

| Tool | What it does |
| --- | --- |
| `add_deadline` | Saves a new deadline with a title, a due date in your own words and an optional subject. It refuses a title you already have, and dates that are unclear, do not exist or have already passed. The reply spells out the full date so you can spot a mistake. |
| `list_deadlines` | Lists every saved deadline, soonest first, including finished ones. |
| `next_deadline` | Finds the next deadline that is not finished and has not passed yet. |
| `delete_deadline` | Permanently deletes a deadline. |
| `mark_done` | Marks a deadline as finished. It stays in the list but no longer shows up in reminders or as your next deadline. |
| `get_reminders` | Finds unfinished deadlines that are overdue, due today or due soon. "Soon" means the next 7 days unless you ask about a different period, from 1 to 60 days. |
| `export_calendar` | Saves every unfinished deadline to `deadlines.ics`, a calendar file you can import into Google Calendar, Outlook or your phone. See [Export to your calendar](#export-to-your-calendar). |

Titles are matched as whole titles. Upper and lower case, extra spaces and look alike characters (such as a full width letter from an Asian keyboard) are ignored, so "assignment 1" finds "Assignment 1". Part of a title is not enough, so "Assignment" does not find "Assignment 1".

Groot only helps with deadlines, and it is told to say so politely if you ask about anything else.

## Date phrases it understands

Groot is told to pass your words to `add_deadline` exactly as you typed them. The code in `deadline_agent/tools.py` then turns them into a saved date. Everything here is Sydney time.

These are real results from the code with the clock set to **Thursday 5 Nov 2026, 10:00 AM**, the same moment most of the tests use.

| You type | Saved as |
| --- | --- |
| `today` | Thursday 5 Nov 2026, 11:59 PM |
| `tomorrow` | Friday 6 Nov 2026, 11:59 PM |
| `in 3 days` | Sunday 8 Nov 2026, 11:59 PM |
| `in a week` | Thursday 12 Nov 2026, 11:59 PM |
| `in 2 weeks` | Thursday 19 Nov 2026, 11:59 PM |
| `in 3 hours` | Thursday 5 Nov 2026, 1:00 PM |
| `in 30 minutes` | Thursday 5 Nov 2026, 10:30 AM |
| `friday` or `fri` | Friday 6 Nov 2026, 11:59 PM |
| `next friday` | Friday 13 Nov 2026, 11:59 PM |
| `thursday` (today is Thursday) | Thursday 12 Nov 2026, 11:59 PM |
| `20 nov`, `20th november` or `20/11` | Friday 20 Nov 2026, 11:59 PM |
| `20 nov 2026` or `20/11/2026` | Friday 20 Nov 2026, 11:59 PM |
| `20 jan` | Wednesday 20 Jan 2027, 11:59 PM |
| `end of the week` | Sunday 8 Nov 2026, 11:59 PM |
| `end of next week` | Sunday 15 Nov 2026, 11:59 PM |
| `2026-11-20 14:30` | Friday 20 Nov 2026, 2:30 PM |
| `5pm` | Thursday 5 Nov 2026, 5:00 PM |
| `next friday 5pm` | Friday 13 Nov 2026, 5:00 PM |
| `tomorrow 5:30pm` or `tomorrow 5.30pm` | Friday 6 Nov 2026, 5:30 PM |
| `20 nov 17:00` | Friday 20 Nov 2026, 5:00 PM |
| `friday noon` | Friday 6 Nov 2026, 12:00 PM |
| `friday midnight` | Friday 6 Nov 2026, 11:59 PM |
| `tomorrow 12am` | Friday 6 Nov 2026, 12:00 AM |

The rules behind the table:

- **No time means the end of the day.** A deadline with no time is due at 11:59 PM, so it still counts as upcoming all of that day.
- **A time on its own means today.** "5pm" is 5 PM today.
- **Times** can be `5pm`, `5 pm`, `5:30pm`, `5.30pm`, `17:00`, `noon`, `midday` or `midnight`. "midnight" means 11:59 PM on that same day, and "12am" means the very start of the day. A time like `5:30` with no am or pm is refused with a question, because it could be morning or evening. `17:30` works.
- **Adding a time** works with `today`, `tomorrow`, `in 3 days`, a weekday or a date, as in `in 3 days 9am`. It does not work with `in 3 hours`, `in 30 minutes` or `end of the week`.
- **Day comes before month**, as in Australia. `12/11` is 12 November.
- **A day and month with no year** means the next time that date comes round. In November, `20 jan` means January next year. A year you type is always used. When a date lands in a later year, the reply points it out, for example "That's in 2027, not this year."
- **Short names** work for weekdays (`mon`, `tue`, `tues`, `wed`, `thu`, `thur`, `thurs`, `fri`, `sat`, `sun`) and months (`jan` to `dec`, plus `sept`).
- **Small words are ignored.** Upper and lower case, commas and the words "due", "by", "on" and "at" make no difference, so `due on Friday at 5pm` works.
- **Numbers** in "in 3 days" go up to 999, and "a" or "an" also work, as in "in a week" or "in an hour".

Some things are refused. Nothing is saved, and the reply says why:

- **Phrases it does not know**, such as `next week`, `the day after tomorrow`, `nov 20` (month first), `20/11/26` (a two digit year) or `20-11-2026`. The reply gives examples of what to type: "I couldn't work out a date from 'next week'. Try something like 'next friday 5pm', 'in 3 days' or '20 nov'."
- **Dates that do not exist**, such as `30 feb`. February has already passed in November, so it looks at next year, and the reply starts with "30 Feb 2027 doesn't exist, so please check the day and month." followed by the same examples.
- **Dates in the past**, such as `9am` when it is already 10 AM. The reply shows the date it understood so you can check it: "'9am' would be Thursday 5 Nov 2026, 9:00 AM, which is already in the past. Please check the date and time."

### "friday" vs "next friday"

Weeks run from Monday to Sunday.

- **"friday"** is the next Friday after today. It is never today, so on a Friday it means a week from today.
- **"next friday"** is the Friday in next week.

Here is what the code gives for every day of one week:

| Today | "friday" | "next friday" |
| --- | --- | --- |
| Monday 2 Nov 2026 | Friday 6 Nov | Friday 13 Nov |
| Tuesday 3 Nov 2026 | Friday 6 Nov | Friday 13 Nov |
| Wednesday 4 Nov 2026 | Friday 6 Nov | Friday 13 Nov |
| Thursday 5 Nov 2026 | Friday 6 Nov | Friday 13 Nov |
| Friday 6 Nov 2026 | Friday 13 Nov | Friday 13 Nov |
| Saturday 7 Nov 2026 | Friday 13 Nov | Friday 13 Nov |
| Sunday 8 Nov 2026 | Friday 13 Nov | Friday 13 Nov |

So from Monday to Thursday the two are a week apart, and from Friday to Sunday they mean the same day. The same rule works for every weekday. For example, on a Sunday both "monday" and "next monday" mean tomorrow.

## Reminders at the start of a chat

Every time ADK sends a request to Gemini, it first calls `groot_instruction` in `deadline_agent/agent.py`. This adds today's date in Sydney and a "Current reminders" block to Groot's instruction. The block lists every unfinished deadline that is overdue, due today or due in the next 7 days, with a phrase such as "in 3 hours", "tomorrow" or "2 days overdue". For example:

```
- Overdue: "Essay" (Writing), due Tuesday 3 Nov 2026, 11:59 PM (2 days overdue)
- Due today: "Quiz" (Maths), due Thursday 5 Nov 2026, 1:00 PM (in 3 hours)
- Due soon: "Report", due Friday 6 Nov 2026, 11:59 PM (tomorrow)
```

Groot is told to mention these briefly and kindly after its greeting at the start of a conversation, not to repeat them on later turns unless you ask, and not to invent any when there are none. The block shows at most 10 deadlines and then says how many more there are. Finished deadlines never appear. The block and the `get_reminders` tool use the same code, so they always agree. The second example chat below shows what this looks like.

On a different day, the phrase counts whole calendar days. On the same day, it counts hours, or minutes when less than an hour is left. Part hours are dropped, so it never promises more time than there really is.

## Where your deadlines are saved

Deadlines are saved in `deadlines.json` in the project folder, next to this README. The file is created the first time you save a deadline. It is read at the start of every tool call and written after every change, so your deadlines are still there after a restart. A file with two deadlines looks like this:

```json
[
  {
    "title": "Essay",
    "due_date": "2026-11-20",
    "subject": "Writing",
    "done": false
  },
  {
    "title": "Quiz 2",
    "due_date": "2026-11-13 17:00",
    "subject": "Machine Learning",
    "done": false
  }
]
```

The `due_date` is Sydney time, either `YYYY-MM-DD` (due by 11:59 PM that day) or `YYYY-MM-DD HH:MM`.

- To see the file, run `cat deadlines.json` on Linux or macOS, or `type deadlines.json` on Windows, from the project folder.
- To use a different file, set the `DEADLINES_FILE` environment variable to its path. The tests do this, so they never touch your real deadlines.
- `deadlines.json` is listed in `.gitignore`, so your personal deadlines are not committed.
- `adk web` keeps its own chat history in `deadline_agent/.adk/session.db`, which is also ignored by git.

**If the file cannot be read.** A file with broken JSON, missing fields or a date in the wrong form does not stop Groot. It is treated as an empty list, and reading it never changes it. The next time something is saved, the old file is first copied to a new file in the same folder called `deadlines.json.corrupt-YYYYMMDD-HHMMSS`, then a fresh list is saved. If that name is already taken, `-2`, `-3` and so on are added, so an older copy is never overwritten. The success message names the copy, so Groot can tell you about it. If the file cannot even be copied (for example, you are not allowed to open it), the save is refused and the file is left alone, with the message "I couldn't save your deadlines (...), so nothing has changed." A file saved with a byte order mark, which Windows PowerShell 5.1 and older versions of Notepad add, loads normally.

## Export to your calendar

Ask Groot something like "add these to my calendar" or "export my deadlines". The `export_calendar` tool saves every unfinished deadline to `deadlines.ics` in the project folder, next to `deadlines.json`. To save it somewhere else, set the `DEADLINES_ICS_FILE` environment variable to the path you want. It is a standard iCalendar file. Each deadline becomes a one minute event that starts at its due time (11:59 PM when it has no time), with the subject in its notes and a reminder 1 day before. Finished deadlines are left out, and if nothing is unfinished, no file is made. `deadlines.ics` is listed in `.gitignore`, so it is not committed.

To import it:

- **Google Calendar.** On a computer, open Google Calendar. In the top right, click the gear icon and then **Settings**. In the menu on the left, click **Import & export**. Click **Select file from your computer**, pick `deadlines.ics`, choose which calendar to add it to and click **Import**.
- **Android phone.** Import the file into Google Calendar on a computer as above. The events then show up in the Google Calendar app on any phone signed in to the same Google account.
- **iPhone.** If you use Google Calendar on your iPhone, do the same as for Android. For Apple's Calendar app, email `deadlines.ics` to yourself, open the email in the Mail app, tap the file and then tap **Add All**.
- **Outlook.** In Outlook on the web or Outlook.com, open your calendar, click **Add calendar**, then **Upload from file**.

Good to know:

- Each deadline keeps the same ID every time you export, because the ID is made from its title. Calendar apps use this ID to recognise an event they already have, so importing a newer file into the same calendar should update those events instead of adding copies.
- Importing never deletes anything. A deadline you finish or delete in Groot stays in your calendar until you delete it there.
- Google Calendar may use your own notification settings instead of the 1 day reminder in the file.

## Supported file types

The outline reader (`deadline_agent/outline.py`) reads subject outlines in all of these formats. `deadline_agent/documents.py` works out what a file really is from its contents, so a file with the wrong ending is still read the right way. The name only matters for plain text, to tell a `.csv` file from a `.txt` file.

| Format | Endings | What Gemini gets |
| --- | --- | --- |
| PDF | `.pdf` | The file itself |
| Picture | `.png`, `.jpg`, `.jpeg`, `.webp` | The picture itself, for example a photo or screenshot of an outline |
| Word | `.docx`, `.doc` | The text of every paragraph and every table, in order |
| PowerPoint | `.pptx`, `.ppt` | The text and tables of every slide under a "Slide 1", "Slide 2" heading, and the speaker notes |
| Excel | `.xlsx`, `.xls` | Every sheet under a "Sheet: name" heading, one row per line. Only values are read, never formulas, and dates and percentages look the way Excel shows them |
| OpenDocument | `.odt`, `.odp`, `.ods` | The same as Word, PowerPoint and Excel |
| CSV | `.csv` | Read like one sheet |
| Text | `.txt`, `.md` | The text as it is |
| Web page | `.html`, `.htm` | The words a browser would show, without scripts and styles |

Wherever an outline is sent as text, each table row stays on one line with its cells separated by a vertical bar, like `Skills Test 1 | 10% | Week 2`, because the assessment table is the most important part.

**From Google Docs, Sheets or Slides.** Groot cannot open a Google link, so download a copy first. Open the file and choose **File**, then **Download**, then **Microsoft Word (.docx)** in Docs, **Microsoft Excel (.xlsx)** in Sheets or **Microsoft PowerPoint (.pptx)** in Slides. **PDF Document (.pdf)** works in all three.

**Old .doc and .ppt files need LibreOffice.** Groot turns them into `.docx` or `.pptx` with [LibreOffice](https://www.libreoffice.org), which is free, and then reads that copy. The `soffice` or `libreoffice` command must be on your PATH. On Linux the LibreOffice package adds it for you. On Windows add `C:\Program Files\LibreOffice\program` to PATH, and on macOS add `/Applications/LibreOffice.app/Contents/MacOS`. Without LibreOffice, Groot says "This is an old Word/PowerPoint file. Save it as .docx, .pptx or PDF and try again." Old `.xls` files do not need LibreOffice.

**What is refused.** Nothing inside a file is ever run.

- Files with macros are always refused: `.docm`, `.xlsm` and `.pptm` files, and any Word, Excel or PowerPoint file that holds macros, whatever its name.
- Files locked with a password, empty files and kinds not in the table get a one sentence message that lists the formats above. A PDF that is only locked against editing or printing still opens without a password, so it is read as usual.
- A file can be at most 10 MB. Word, PowerPoint, Excel and OpenDocument files are zip files inside, so before one is opened Groot checks that it unpacks to at most 50 MB and has at most 1,000 parts, which stops "zip bombs". Spreadsheets are read up to 5,000 rows and 50,000 cells, and at most 200,000 characters of text are sent to Gemini. When the text is cut, a note at the end tells Gemini.

## Example chats

These two chats are real output from a test run with the real Gemini model.

**Chat 1.** The student's deadline file started empty.

> **Student:** Add Quiz 2 due next friday 5pm for Machine Learning
>
> *Tool call:* `add_deadline(title='Quiz 2', due_date='next friday 5pm', subject='Machine Learning')`
>
> **Groot:** Added **Quiz 2** for **Machine Learning**, due Friday, 13 November 2026 at 5:00 PM!
>
> **Student:** what's my next deadline?
>
> *Tool call:* `next_deadline()`
>
> **Groot:** Your next deadline is **Quiz 2** for **Machine Learning**, due on Friday, 13 November 2026 at 5:00 PM.

Groot passed "next friday 5pm" to the tool exactly as typed, and the Python code worked out the date. The tool's own message was "Saved 'Quiz 2', due Friday 13 Nov 2026, 5:00 PM.", which Groot reworded.

**Chat 2.** The saved file held an overdue Quiz 1, a Lab report due the next day and an Essay due in 3 days. It was the evening of Tuesday 3 Nov 2026 in Sydney.

> **Student:** hello
>
> **Groot:** Hey there! I'm Agent Groot, your friendly study assistant. I'm here to help you keep track of your assignment and exam deadlines so you never get caught by surprise!
>
> Just a quick heads-up on your upcoming items:
> - You have a **Quiz 1** for Data Analytics that was due a couple of days ago.
> - Your **Lab report** for Machine Learning is due tomorrow at 5:00 PM.
> - Your **Essay** for Writing is coming up this Friday.
>
> How can I help you today?

No tool call appears in this chat. Groot took the reminders from the block in its instruction.

## Setup

You need:

- **Python 3.10 or newer.** This is the oldest version that google-adk 2.11.0 supports.
- **A Gemini API key.** You can get one for free from Google AI Studio. Google's guide is at [Get a Gemini API key](https://ai.google.dev/gemini-api/docs/api-key).
- An internet connection, to install the packages and to talk to Gemini.

Both setup scripts do the same four things. They check your Python version, create a virtual environment in `.venv`, install `requirements.txt`, and then ask for your key and save it in `deadline_agent/.env`. If `deadline_agent/.env` already exists, they ask before replacing it, and keep it unless you answer `y`.

### Windows

1. Install Python 3.10 or newer from python.org and tick "Add python.exe to PATH" on the first screen.
2. Download or clone this project.
3. Double click `setup_windows.bat` and paste your key when it asks. The key shows on screen while you paste it.

### Linux and macOS

```bash
git clone https://github.com/Richardyan701/deadline_tracker_agent.git
cd deadline_tracker_agent
./setup.sh
```

The key stays hidden while you paste it, and `deadline_agent/.env` is made readable only by your user account (permission 600). If `python3` on your computer is older than 3.10, install a newer Python and tell the script which one to use, for example `PYTHON=python3.12 ./setup.sh`.

### What the setup writes

`deadline_agent/.env` holds two lines, the same two that ADK's own `adk create` command writes for a Gemini API key:

```
GOOGLE_GENAI_USE_ENTERPRISE=0
GOOGLE_API_KEY=your key
```

`deadline_agent/.env.example` shows the same thing with a placeholder key. Never commit `.env`, because it holds your key. It is already listed in `.gitignore`, and the GitHub Actions check fails if one is committed.

The scripts do not run `adk create`, because the agent already exists in `deadline_agent`, and `adk create` would offer to replace `agent.py` with a blank template.

## Running it

The start files are the easy way. On Windows, double click `start_groot.bat`. On Linux or macOS, run `./start_groot.sh` from the project folder. Each one checks that the setup has been run, starts the ADK web app, waits until <http://127.0.0.1:8000> answers, opens it in your browser and tells you to press Ctrl+C to stop it. On Windows, the window may then ask "Terminate batch job (Y/N)?", and either answer is fine.

To start it by hand instead, open Command Prompt or PowerShell in the project folder on Windows (in File Explorer you can type `cmd` in the address bar and press Enter), then run:

```
.\.venv\Scripts\python.exe -m google.adk.cli web --port 8000
```

On Linux or macOS:

```bash
.venv/bin/python -m google.adk.cli web --port 8000
```

This runs the same program as `adk web --port 8000`, but through Python, because some antivirus programs block `.venv\Scripts\adk.exe`. Then open <http://127.0.0.1:8000> in your browser and say hello. Groot is already chosen, because it is the only agent in the project. Press Ctrl+C in the terminal to stop it. `adk web` is a local development server with no login, so only run it on your own computer.

## Running the tests

The tests need no API key and no internet. From the project folder on Windows:

```
.\.venv\Scripts\python.exe -m pytest
```

On Linux or macOS:

```bash
.venv/bin/python -m pytest
```

The last line should start with `383 passed`.

## Troubleshooting

Start with the setup checker. It looks at your Python, the packages, your key file, port 8000, the deadlines file and the Sydney time zone, and gives a one line fix for anything that is wrong. It never changes a file and sends nothing over the internet. On Windows:

```
.\.venv\Scripts\python.exe -m deadline_agent.check_setup
```

On Linux or macOS:

```bash
.venv/bin/python -m deadline_agent.check_setup
```

Add `--online` to also send one tiny real request to Gemini, which proves your key works. That uses 1 of your 20 free requests for today, so the checker only sends it when every other check passed.

When Gemini cannot answer, Groot now says why in the chat instead of showing a long red error. The terminal where Groot runs still shows the full error, after a line starting "Gemini failed, so Groot showed a friendly reply instead".

- **"Gemini's free daily limit is used up. It resets in about 5 hours 37 minutes (around 7:00 PM Sydney time). Your saved deadlines are safe."** The free tier allows 20 requests a day for each model, which is roughly 8 to 10 messages that use a tool. Google resets it at midnight Pacific time, which is between 5 PM and 7 PM in Sydney. The wait in the message comes from Google's own reply.
- **"That was a lot of messages in a minute. Wait about 30 seconds and try again."** The free tier allows 5 requests a minute, and a message that uses a tool needs two of them. Wait as long as it says.
- **"Gemini's free limit has been reached for now."** Google said a limit was reached but not which one. Wait a minute and try again. If it keeps happening, the daily limit is probably used up.
- **"I can't find your Gemini API key"** (the terminal shows `No API key was provided`). This usually means `deadline_agent/.env` is missing. Run the setup script again, then restart Groot.
- **"Gemini says your API key is not valid"** (the terminal shows `API key not valid. Please pass a valid API key.`). The key in `deadline_agent/.env` is wrong, often because it was not copied in full. Run the setup script again, answer `y` to replace the file, then restart Groot.
- **"Gemini took too long to answer"** (the terminal shows `504 DEADLINE_EXCEEDED`). Send your message again.
- **Any other error**, such as `503 UNAVAILABLE` when Gemini is overloaded, still shows up as a red error in the chat and in the terminal, the same as before.
- **`This Python is older than 3.10`** (setup.sh) or **`Your Python is older than 3.10`** (setup_windows.bat). Install Python 3.10 or newer. On Linux or macOS you can then run `PYTHON=python3.12 ./setup.sh`, using the name of your newer Python.
- **`Could not find python3`** (setup.sh) or **`Python was not found`** (setup_windows.bat). Install Python. On Windows, tick "Add python.exe to PATH" in the installer.
- **`Access is denied` when you start `adk.exe`** (Windows). Some antivirus programs block `.venv\Scripts\adk.exe`. The start files avoid it by starting the same server through Python, and you can do the same by hand with `.venv\Scripts\python.exe -m google.adk.cli web --port 8000`. On Linux or macOS the same command is `.venv/bin/python -m google.adk.cli web --port 8000`.

## How it is built

```
deadline_agent/
  agent.py         Groot itself: its model, its instruction and its list of tools
  tools.py         the tools, the date rules and the saving code
  .env.example     example key file (the real .env is never committed)
tests/             383 tests, no API key needed
.github/workflows/tests.yml
requirements.txt   google-adk 2.11.0, fastapi 0.141.1, httpx 0.28.1, icalendar 7.3.0, pypdf 6.21.4,
                   pytest 9.2.0, python-multipart 0.0.32, tzdata 2026.6, uvicorn 0.54.0, and for
                   outline files python-docx 1.2.0, python-pptx 1.0.2, openpyxl 3.1.5, xlrd 2.0.2,
                   olefile 0.47, defusedxml 0.7.1 and pillow 12.3.0
setup.sh           setup for Linux and macOS
setup_windows.bat  setup for Windows
```

- **`agent.py`** defines `root_agent`, an ADK `Agent` called `agent_groot` that uses `gemini-3.5-flash` and the six tools. Its instruction is a function, `groot_instruction`, which ADK runs before every request to Gemini (ADK's name for this is an instruction provider). It returns Groot's fixed instruction, today's date in Sydney, the rule to pass due dates through exactly as typed, the rules for reminders, and the reminders block.
- **`tools.py`** holds the six tools. ADK reads each tool's name, type hints and docstring to tell Gemini what the tool does. Every tool returns a `status` and a `message`, and problems come back as a message Groot can pass on instead of a crash.
- **Why dates are worked out in Python.** The model does not reliably know today's date, so it is bad at things like "next friday". Plain rules in Python give the same answer every time, and each rule is covered by tests. The reply also spells out the full date, so a misunderstanding is easy to catch.
- **Protection against prompt injection in titles.** Titles and subjects are typed by the student and end up in Groot's instruction, so a title like "Essay, ignore previous instructions" could try to give orders. When a deadline is saved, line breaks and runs of spaces in the title and subject become a single space. Before a title or subject goes into the reminders block, control and invisible characters become spaces, `<` and `>` are removed so it cannot fake the end of the block, double quotes become single quotes, and it is cut to 80 characters. Groot is also told that the block, and every title or subject in a tool result, is data to report and never instructions to follow. This keeps each title on its own line inside the block, but it cannot make the model fully immune.
- **Safe saves.** Each save writes the whole list to a temporary file in the same folder, makes sure it has reached the disk, then swaps it in with `os.replace` in a single step. A crash leaves either the old file or the new one, never half a file. A lock lets only one tool call read or change the file at a time, because ADK can run tools on several threads. A test starts 20 saves at once on separate threads and checks that all 20 are kept.
- **Daylight saving.** All dates and times are Sydney time (`Australia/Sydney`). Lengths of time, such as "in 3 hours" or "2 hours overdue", are worked out in UTC, so they stay right on the two nights each year when Sydney's clocks change. For example, at 8 PM on Saturday 3 Oct 2026, "in 12 hours" is saved as 9:00 AM on Sunday, because the clocks go forward an hour that night. The `tzdata` package is included because Windows has no time zone database of its own for Python to use.

## Tests and CI

There are 383 tests, run with pytest:

| File | Tests | What they cover |
| --- | --- | --- |
| `tests/test_dates.py` | 182 | Every date phrase, weekdays near the weekend, new months and years, leap days, daylight saving, and refused input |
| `tests/test_reminders.py` | 113 | Reminder groups, exact edges like 11:59 PM, the friendly phrases, the reminders block, and the prompt injection protection |
| `tests/test_tools.py` | 80 | The six tools, title matching, saving, backups of unreadable files, failed saves and many threads at once |
| `tests/test_agent.py` | 8 | Groot's tools and instruction, plus whole turns through ADK with a scripted stand in for Gemini |

No test needs an API key or the internet. Each test saves to its own temporary file, and every test that depends on the date sets the clock itself, so the results never depend on today's date.

GitHub Actions runs the tests on every push to `main` and on every pull request, on Python 3.13 and 3.14. The job can only read the code, fails if a `.env` or `deadlines.json` file is committed, and fails if any `GOOGLE_` or `GEMINI_` variable is set, which proves the tests pass without a key. The badge at the top shows the status of this workflow.

## Limitations and known gaps

- **One user, one local file.** There are no accounts. Everyone using the same copy shares one `deadlines.json`, and nothing syncs between devices.
- **The Gemini free tier is limited** to about 5 requests per minute and 20 requests per day for each model. A message that uses a tool costs at least two requests, one to choose the tool and one to reply, so the free tier gives you roughly 8 to 10 messages that use a tool each day, and a few quick messages in a row can hit the per minute limit. When a limit is reached, Groot says which one and when to try again (see [Troubleshooting](#troubleshooting)). Google sets these limits and can change them. See [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
- **Sydney time only.** The time zone is fixed in the code.
- **English only.** Date words like "friday" and "tomorrow" must be in English.
- **No editing.** To change a deadline, delete it and add it again.
- **No past deadlines.** You cannot add a deadline whose time has already passed.
- **Reminders only appear in a chat.** Groot does not send notifications.
- **The Windows setup script shows your key on screen** while you paste it.

## Built with

Python, [Google ADK](https://github.com/google/adk-python) 2.11.0, Gemini 3.5 Flash, pytest and GitHub Actions.

## Licence

MIT. See [LICENSE](LICENSE).
