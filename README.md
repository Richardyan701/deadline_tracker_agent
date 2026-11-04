# Agent Groot: a study deadline assistant

[![Tests](https://github.com/Richardyan701/deadline_tracker_agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Richardyan701/deadline_tracker_agent/actions/workflows/tests.yml)

Agent Groot keeps track of your university assignment and exam deadlines. You can tell it about a deadline in your own words in a chat, like "Quiz 2 due next friday 5pm", add one on Groot's home page, or let Groot find every deadline in your UTS subject outlines. It saves them in a file on your computer, reminds you about anything overdue or due in the next 7 days, and can put them in your calendar. It runs on Google's Agent Development Kit (ADK) with the Gemini 3.5 Flash model. The date maths is done in plain Python code instead of by the model, so a date like "next friday" or "week 7" always follows the same rules. It was built by Richard, a first year artificial intelligence student at UTS in Sydney.

## Quick start

1. **Run the setup script once.** On Windows, double click `setup_windows.bat`. On Linux or macOS, run `./setup.sh`. It installs everything and asks for your free Gemini API key. [Setup](#setup) says what you need first.
2. **Start Groot.** On Windows, double click `start_groot.bat`. On Linux or macOS, run `./start_groot.sh`. Your browser opens Groot's home page at <http://127.0.0.1:8000/groot>.
3. **Use it.** On the home page you can add deadlines, mark them done, export them to your calendar, import them from your subject outlines, or click **Chat with Groot** and say hello. Press Ctrl+C in the start window to stop Groot.

If anything goes wrong, run the setup checker (`.venv\Scripts\python.exe -m deadline_agent.check_setup` on Windows, `.venv/bin/python -m deadline_agent.check_setup` on Linux and macOS) and follow the fix it gives under each cross.

## What it can do

Groot is one web app that runs on your own computer. It has three pages, and all three use the same deadlines file, so a change on one shows up on the others.

| Page | Address | Uses Gemini? |
| --- | --- | --- |
| Home page | <http://127.0.0.1:8000/groot> | Never |
| Chat with Groot | <http://127.0.0.1:8000/dev-ui/?app=deadline_agent> | For every message you send |
| Import from outlines | <http://127.0.0.1:8000/groot/import> | Once for each outline, and only when you click Preview |

### The home page

- **Due soon** lists everything unfinished that is overdue, due today or due in the next 7 days, with phrases like "in 3 hours" or "2 days overdue". It uses the same code as the chat's reminders, so the two always agree.
- **All deadlines** lists every deadline, soonest first. Each one has a **Delete** button, which asks you first, and each unfinished one also has a **Mark done** button. Finished deadlines are greyed out.
- **Add a deadline** takes a title, a due date in plain words like "next friday 5pm" and an optional subject. It follows the same rules as the chat, see [Date phrases it understands](#date-phrases-it-understands), and shows the same message, good or bad.
- **Export to calendar** downloads `deadlines.ics`, see [Export to your calendar](#export-to-your-calendar).
- **Import from outlines** and **Chat with Groot** open the other two pages.

### The chat

The chat is the one ADK gives every agent, with Groot already chosen. If a box asks about sharing usage data with Google, either button is fine. Say hello, and while you have nothing saved yet, Groot also suggests a few things to type. Groot has seven tools. Gemini reads what you type and decides which tool to call.

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

Groot only helps with deadlines, and it is told to say so politely if you ask about anything else. If you ask about your subject outlines, or attach a file in the chat, Groot points you to the Import from outlines page instead of reading dates from the file itself, because only that page knows the UTS calendar.

### Import from outlines

Drop in your subject outlines, and Groot lists every assessment deadline it finds with the real date from the UTS calendar. You check the list, and only the rows you tick are saved. [Importing deadlines from your outlines](#importing-deadlines-from-your-outlines) explains every step.

## Date phrases it understands

Groot is told to pass your words to `add_deadline` exactly as you typed them. The code in `deadline_agent/tools.py` then turns them into a saved date. The home page's add form uses the same code. Everything here is Sydney time.

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

Groot is told to mention these briefly and kindly after its greeting at the start of a conversation, not to repeat them on later turns unless you ask, and not to invent any when there are none. The block shows at most 10 deadlines and then says how many more there are. Finished deadlines never appear. The block, the `get_reminders` tool and the home page's Due soon list use the same code, so they always agree. The second example chat below shows what this looks like.

On a different day, the phrase counts whole calendar days. On the same day, it counts hours, or minutes when less than an hour is left. Part hours are dropped, so it never promises more time than there really is.

## Where your deadlines are saved

Deadlines are saved in `deadlines.json` in the project folder, next to this README. The file is created the first time you save a deadline. The chat, the home page and the outline import all go through the same tools, which read the file at the start of every action and write it after every change, so your deadlines are still there after a restart. A file with two deadlines looks like this:

```json
[
  {
    "title": "Essay",
    "due_date": "2026-11-20",
    "subject": "Writing",
    "done": false
  },
  {
    "title": "33130 Skills Test 1",
    "due_date": "2026-08-07 23:59",
    "subject": "33130 Mathematics 1",
    "done": false
  }
]
```

The `due_date` is Sydney time, either `YYYY-MM-DD` (due by 11:59 PM that day) or `YYYY-MM-DD HH:MM`.

- To see the file, run `cat deadlines.json` on Linux or macOS, or `type deadlines.json` on Windows, from the project folder.
- To use a different file, set the `DEADLINES_FILE` environment variable to its path. The tests do this, so they never touch your real deadlines.
- `deadlines.json` is listed in `.gitignore`, so your personal deadlines are not committed.
- The chat keeps its own history in `deadline_agent/.adk/session.db`, which is also ignored by git.

**If the file cannot be read.** A file with broken JSON, missing fields or a date in the wrong form does not stop Groot. It is treated as an empty list, and reading it never changes it. The next time something is saved, the old file is first copied to a new file in the same folder called `deadlines.json.corrupt-YYYYMMDD-HHMMSS`, then a fresh list is saved. If that name is already taken, `-2`, `-3` and so on are added, so an older copy is never overwritten. The success message names the copy, so Groot can tell you about it. If the file cannot even be copied (for example, you are not allowed to open it), the save is refused and the file is left alone, with the message "I couldn't save your deadlines (...), so nothing has changed." A file saved with a byte order mark, which Windows PowerShell 5.1 and older versions of Notepad add, loads normally.

## Export to your calendar

Click **Export to calendar** on the home page, or ask Groot something like "add these to my calendar". Either way, every unfinished deadline is saved to `deadlines.ics` in the project folder, next to `deadlines.json`, and the home page also downloads it for you. To save it somewhere else, set the `DEADLINES_ICS_FILE` environment variable to the path you want. It is a standard iCalendar file. Each deadline becomes a one minute event that starts at its due time (11:59 PM when it has no time), with the subject in its notes and a reminder 1 day before. Finished deadlines are left out, and if nothing is unfinished, no file is made. `deadlines.ics` is listed in `.gitignore`, so it is not committed.

To import it:

- **Google Calendar.** On a computer, open Google Calendar. In the top right, click the gear icon and then **Settings**. In the menu on the left, click **Import & export**. Click **Select file from your computer**, pick `deadlines.ics`, choose which calendar to add it to and click **Import**.
- **Android phone.** Import the file into Google Calendar on a computer as above. The events then show up in the Google Calendar app on any phone signed in to the same Google account.
- **iPhone.** If you use Google Calendar on your iPhone, do the same as for Android. For Apple's Calendar app, email `deadlines.ics` to yourself, open the email in the Mail app, tap the file and then tap **Add All**.
- **Outlook.** In Outlook on the web or Outlook.com, open your calendar, click **Add calendar**, then **Upload from file**.

Good to know:

- Each deadline keeps the same ID every time you export, because the ID is made from its title. Calendar apps use this ID to recognise an event they already have, so importing a newer file into the same calendar should update those events instead of adding copies.
- Importing never deletes anything. A deadline you finish or delete in Groot stays in your calendar until you delete it there.
- Google Calendar may use your own notification settings instead of the 1 day reminder in the file.

## Importing deadlines from your outlines

The Import from outlines page (<http://127.0.0.1:8000/groot/import>) works in four steps.

1. **Choose your files.** Drag 1 to 8 subject outlines onto the box, or click **Choose outline files**. Each one can be up to 10 MB and any kind of file in [Supported file types](#supported-file-types), for example the PDF from UTS, a Word file or a photo of the assessment table. You can also add:
   - **Your UTS timetable**, as the PDF export of your timetable. Only a PDF works here. Groot reads it with plain code to find the day and time of your tutorials, so it never uses Gemini.
   - **Your Canvas calendar feed link.** In Canvas, open Calendar, then Calendar Feed, and copy the link. Groot fetches it once to get Canvas's exact due dates. It only accepts `https` links to `canvas.uts.edu.au` or an `instructure.com` address, waits at most 10 seconds, reads at most 2 MB and never follows a redirect. The link works like a password, so Groot never saves it, logs it or shows it again, and you should keep it private.
   - **The session**, Autumn 2026 or Spring 2026. Spring 2026 is chosen at the start.
2. **Preview.** Groot sends each outline to Gemini once, and Gemini lists every assessment item with the outline's own words for when it happens. Gemini is told to copy what the outline says and never to work out a date, and its answer is checked in plain Python before it is used. The page tells you how many requests Preview will use before you click. Every file is checked before anything is sent: a kind of file Groot cannot read stops the whole preview straight away, and a file that turns out to have no readable text is reported without using a request. One outline that Gemini cannot read never stops the others.
3. **Check.** The review table has one row for each deadline, with a note that says where its date came from and how sure Groot is:

   | Status | What it means | Ticked to save? |
   | --- | --- | --- |
   | Exact date | The outline or Canvas gives the day | Yes |
   | Assumed, please check | Groot had to assume part of the date, for example Friday of a week when the outline names no day, or the date falls on a public holiday. The note says what was assumed | Yes |
   | Needs your date | It is held in your tutorial, but Groot could not tell which day. Type a date like `25 aug 9am` in the row | Once you type a date |
   | No date yet | For example an exam in the exam period, or an outline that says to check Canvas | No |
   | Already passed | The date is in the past. It is greyed out, never shown as an error | No |

4. **Save.** Click **Save ticked deadlines**. Each row goes through `add_deadline`, the same as adding a deadline by hand, so a typed date gets the same checks, and each row says whether it was saved. One row that cannot be saved never stops the others. Titles start with the subject code, like `33130 Skills Test 1`, so items in different subjects never clash.

### How dates are decided

Outlines give most dates as teaching weeks, like "due in week 2". The weeks are not evenly spaced, because each session has a study week (StuVac) in the middle that has no number. So the dates come from the official UTS 2026 calendar in `deadline_agent/uts_calendar.py`, never from counting weeks. Weeks start on Monday.

| Session | Week 1 starts | StuVac | Exams |
| --- | --- | --- | --- |
| Autumn 2026 | Monday 16 Feb | 6 to 12 Apr, and 18 to 24 May | 25 May to 12 Jun |
| Spring 2026 | Monday 27 Jul | 21 to 27 Sep, and 26 Oct to 1 Nov | 2 to 20 Nov |

The rules, for each item:

- **A calendar date** is used as it is, at 11:59 PM when the outline gives no time.
- **A week with a day**, like "Monday of week 9", is that day. **A week with no day** is Friday of that week, at 11:59 PM or at the time the outline gives, and marked Assumed.
- **In your tutorial in a given week** uses the day and start time of your tutorial from your timetable (your Tut class, or your Wrk class if the subject has no Tut). With no timetable, or two different tutorial times, the row needs your date.
- **Every week from week A**, like weekly quizzes, becomes one row for each teaching week up to the last week the outline gives (week 12 if it gives none), skipping StuVac. They are on Friday unless the outline names a day.
- **An exam in the exam period** has no date yet. The note tells you to check the UTS exam timetable.
- **A Canvas event** that clearly matches a row, in the same subject and with a similar name, gives that row Canvas's exact date. A Canvas event that matches nothing gets a row of its own. When two rows are equally close, nothing is merged and both are flagged so you can check for a duplicate.
- **A date on a NSW public holiday**, like Labour Day on Monday 5 Oct 2026, is flagged in the note and is at best Assumed.

## Supported file types

Both the outline reader (`deadline_agent/outline.py`) and the drop box read subject outlines in all of these formats. `deadline_agent/documents.py` works out what a file really is from its contents, so a file with the wrong ending is still read the right way. The name only matters for plain text, to tell a `.csv` file from a `.txt` file. Your timetable must be a PDF.

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

**Old .doc and .ppt files need LibreOffice.** Groot turns them into `.docx` or `.pptx` with [LibreOffice](https://www.libreoffice.org), which is free, and then reads that copy. The `soffice` or `libreoffice` command must be on your PATH. On Linux the LibreOffice package adds it for you. On Windows add `C:\Program Files\LibreOffice\program` to PATH, and on macOS add `/Applications/LibreOffice.app/Contents/MacOS`. Without LibreOffice, Groot says "This is an old Word/PowerPoint file. Save it as .docx, .pptx or PDF and try again." and nothing is sent to Gemini. Old `.xls` files do not need LibreOffice.

How the conversion is kept safe:

- It happens in a new temporary folder, with a fixed file name, and the folder is deleted straight after. LibreOffice starts inside that folder with a new profile of its own, so your own LibreOffice settings are never used or changed.
- That profile switches off every kind of macro, never updates the links in a Word file when it opens, blocks links from untrusted places, switches off embedded objects (OLE) and DDE links, and sends every web address to a proxy that goes nowhere. So a picture linked to a web address is never fetched. This was tested with LibreOffice 24.2, which without these settings fetched it while converting. An older LibreOffice ignores the settings it does not know yet.
- LibreOffice never sees your Gemini key, because it is left out of the environment LibreOffice gets.
- It has 60 seconds. If it takes longer, Groot stops LibreOffice and every program it started.

**What is refused.** Nothing inside a file is ever run.

- Files with macros are always refused: `.docm`, `.xlsm` and `.pptm` files, and any Word, Excel or PowerPoint file that holds macros, whatever its name.
- Files locked with a password, empty files and kinds not in the table get a one sentence message that lists the formats above. A PDF that is only locked against editing or printing still opens without a password, so it is read as usual.
- A file can be at most 10 MB. Word, PowerPoint, Excel and OpenDocument files are zip files inside, so before one is opened Groot checks that it unpacks to at most 50 MB and has at most 1,000 parts, which stops "zip bombs". Spreadsheets are read up to 5,000 rows and 50,000 cells, and at most 200,000 characters of text are sent to Gemini. When the text is cut, a note at the end tells Gemini.
- From Word, PowerPoint, Excel, OpenDocument and web pages, Groot reads only the text. Entities in the XML inside a file, the trick behind the "billion laughs" and behind reading other files on your computer, are never expanded: they are left out, or the file is refused. Embedded objects, remote templates and links inside a file are never opened or fetched.

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

- **Python 3.11 or newer.** This is the oldest version that every package in `requirements.txt` supports. google-adk 2.11.0 itself works with 3.10, but python-multipart 0.0.33, which reads the files you upload, needs 3.11.
- **A Gemini API key.** You can get one for free from Google AI Studio. Google's guide is at [Get a Gemini API key](https://ai.google.dev/gemini-api/docs/api-key).
- An internet connection, to install the packages and to talk to Gemini.
- **LibreOffice**, only if you want to import old `.doc` or `.ppt` outlines.

Both setup scripts do the same four things. They check your Python version, create a virtual environment in `.venv`, install `requirements.txt`, and then ask for your key and save it in `deadline_agent/.env`. If `deadline_agent/.env` already exists, they ask before replacing it, and keep it unless you answer `y`.

### Windows

1. Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH" on the first screen.
2. Download or clone this project.
3. Double click `setup_windows.bat` and paste your key when it asks. The key shows on screen while you paste it.

### Linux and macOS

```bash
git clone https://github.com/Richardyan701/deadline_tracker_agent.git
cd deadline_tracker_agent
./setup.sh
```

The key stays hidden while you paste it, and `deadline_agent/.env` is made readable only by your user account (permission 600). If `python3` on your computer is older than 3.11, install a newer Python and tell the script which one to use, for example `PYTHON=python3.12 ./setup.sh`.

### What the setup writes

`deadline_agent/.env` holds two lines, the same two that ADK's own `adk create` command writes for a Gemini API key:

```
GOOGLE_GENAI_USE_ENTERPRISE=0
GOOGLE_API_KEY=your key
```

`deadline_agent/.env.example` shows the same thing with a placeholder key. Never commit `.env`, because it holds your key. It is already listed in `.gitignore`, and the GitHub Actions check fails if one is committed.

The scripts do not run `adk create`, because the agent already exists in `deadline_agent`, and `adk create` would offer to replace `agent.py` with a blank template.

## Running it

The start files are the easy way. On Windows, double click `start_groot.bat`. On Linux or macOS, run `./start_groot.sh` from the project folder. Each one checks that the setup has been run, starts Groot's web app, waits until Groot's home page at <http://127.0.0.1:8000/groot> answers, opens it in your browser and tells you to press Ctrl+C to stop it. If Groot cannot start, for example because another program is using port 8000, no browser opens and the window says what went wrong. On Windows, the window may ask "Terminate batch job (Y/N)?" after Ctrl+C, and either answer is fine.

To start it by hand instead, open Command Prompt or PowerShell in the project folder on Windows (in File Explorer you can type `cmd` in the address bar and press Enter), then run:

```
.\.venv\Scripts\python.exe -m web
```

On Linux or macOS:

```bash
.venv/bin/python -m web
```

Then open <http://127.0.0.1:8000/groot> in your browser. Press Ctrl+C in the terminal to stop it.

This one server runs Groot's own pages and ADK's chat together, on port 8000. It only listens on 127.0.0.1, so other computers on your network cannot open it. It is started through Python instead of the `adk` program because some antivirus programs block the programs that pip puts in `.venv\Scripts`. ADK's chat page has no login, so only run Groot on your own computer. `adk web` on its own still starts the chat, but without the home page or the outline drop box, so the start files never use it.

## The Gemini free tier

Groot uses Gemini's free tier, which Google limits to about 5 requests per minute and 20 requests per day for each model. Google resets the daily limit at midnight Pacific time, which is between 5 PM and 7 PM in Sydney. Google sets these limits and can change them, see [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

What uses a request:

| Action | Requests |
| --- | --- |
| A chat message that needs no tool, like "hello" | 1 |
| A chat message that uses a tool, like adding a deadline | At least 2, one to choose the tool and one to reply |
| Each outline when you click Preview on the import page | 1, and the page says how many before you click |
| The setup checker with `--online` | 1, and only when every other check passed |
| The outline evaluation | 1 for each outline |
| The chat evaluation | At least 121 for a full run |

Nothing else ever uses a request: not the home page, adding or changing deadlines there, the calendar export, opening the import page, reading your timetable or Canvas feed, saving ticked rows, the setup checker without `--online`, or the tests. A failed request is never retried on its own. So the free tier gives you roughly 8 to 10 chat messages that use a tool each day, and a few quick messages in a row can hit the per minute limit. When a limit is reached, Groot says which one and when to try again (see [Troubleshooting](#troubleshooting)).

## Measuring how well it works

The tests prove the code follows its rules, but they never talk to Gemini. Two evaluations measure how well the real Gemini model does its part. Both need your key, use your free requests, wait between requests so they send at most 4 in a minute (the chat evaluation's `--per-minute` changes that for a paid key), and write their scores to a `results.md` file.

- **The outline evaluation** (`eval/run_eval.py`) sends real UTS outlines to the outline reader and compares Gemini's items with an answer key you check by hand: items found, items invented, weights, the timing words, the real dates from the UTS calendar, and silently wrong dates (a wrong date shown as if it were fine). Put the outlines in `eval/outlines/` (they stay off GitHub) and the answer keys in `eval/answer_key/`, then run `.venv/bin/python -m eval.run_eval` on Linux and macOS or `.\.venv\Scripts\python.exe -m eval.run_eval` on Windows. Add `--session AUT2026` for Autumn outlines. [eval/README.md](eval/README.md) explains the answer key format and every score.
- **The chat evaluation** (`eval/chat/run_chat_eval.py`) sends 63 realistic student messages to the real Groot and checks which tools it called and what ended up saved, never its wording. Run `.venv/bin/python -m eval.chat.run_chat_eval --limit 3` first (on Windows, `.\.venv\Scripts\python.exe -m eval.chat.run_chat_eval --limit 3`), then leave out `--limit` for every case. A full run needs at least 121 requests, so on the free tier it takes several days. It saves each finished case and carries on from where it stopped. [eval/chat/README.md](eval/chat/README.md) has the details.

No results are in this repository yet. They appear when you run the evaluations with your own key.

## Running the tests

The tests need no API key and no internet. From the project folder on Windows:

```
.\.venv\Scripts\python.exe -m pytest
```

On Linux or macOS:

```bash
.venv/bin/python -m pytest
```

The last line should say `1317 passed`. A test that needs something your computer does not have is skipped instead, and then the line says how many: the tests that run `start_groot.sh` or a stand-in LibreOffice need Linux or macOS, one test needs LibreOffice itself, and the start file tests also skip while Groot is running on port 8000.

## Troubleshooting

Start with the setup checker. It looks at your Python, the packages, your key file, port 8000, the deadlines file and the Sydney time zone, and gives a one line fix for anything that is wrong. It never changes a file and sends nothing over the internet. On Windows:

```
.\.venv\Scripts\python.exe -m deadline_agent.check_setup
```

On Linux or macOS:

```bash
.venv/bin/python -m deadline_agent.check_setup
```

Each check starts with ✓ or ✗. Where your window cannot show those two characters, for example an old Windows console, or when you save the output to a file on Windows, it shows `[OK]` and `[X]` instead. Add `--online` to also send one tiny real request to Gemini, which proves your key works. That uses 1 of your 20 free requests for today, so the checker only sends it when every other check passed.

When Gemini cannot answer in the chat, Groot says why instead of showing a long red error. The window where Groot runs still shows the full error, after a line starting "Gemini failed, so Groot showed a friendly reply instead".

- **"Gemini's free daily limit is used up. It resets in about 5 hours 37 minutes (around 7:00 PM Sydney time). Your saved deadlines are safe."** The free tier allows 20 requests a day for each model, which is roughly 8 to 10 messages that use a tool. The wait in the message comes from Google's own reply.
- **"That was a lot of messages in a minute. Wait about 30 seconds and try again."** The free tier allows about 5 requests a minute, and a message that uses a tool needs two of them. Wait as long as it says.
- **"Gemini's free limit has been reached for now."** Google said a limit was reached but not which one. Wait a minute and try again. If it keeps happening, the daily limit is probably used up.
- **"I can't find your Gemini API key"** (the window shows `No API key was provided`). This usually means `deadline_agent/.env` is missing. Run the setup script again, then restart Groot.
- **"Gemini says your API key is not valid"** (the window shows `API key not valid. Please pass a valid API key.`). The key in `deadline_agent/.env` is wrong, often because it was not copied in full. Run the setup script again, answer `y` to replace the file, then restart Groot.
- **"Gemini took too long to answer"** (the window shows `504 DEADLINE_EXCEEDED`). Send your message again.
- **Any other error**, such as `503 UNAVAILABLE` when Gemini is overloaded, still shows up as a red error in the chat and in the window.

On the import page, each outline that could not be read gets one sentence in the list under the Preview button:

- **"Gemini's free tier is busy. Wait a minute and try again."** A limit was reached. The other outlines' results are kept, so preview only the ones that failed when you try again.
- **"Groot could not find a valid Gemini API key. Run the setup script again."** The same as the chat's key problems above.
- **"Gemini took too long to read this outline. Try again in a minute."**
- **"This is an old Word/PowerPoint file. Save it as .docx, .pptx or PDF and try again."** Install LibreOffice (see [Supported file types](#supported-file-types)), or save a new copy in another format.
- **"Your timetable could not be used."** Use the PDF export of your UTS timetable, or remove the timetable. Nothing was sent to Gemini.
- **"Your Canvas calendar was not used, so the preview went on without it."** Copy the link again from Canvas, Calendar, Calendar Feed. It must start with `https://`.

Starting Groot:

- **`This Python is older than 3.11`** (setup.sh) or **`Your Python is older than 3.11`** (setup_windows.bat). Install Python 3.11 or newer. On Linux or macOS you can then run `PYTHON=python3.12 ./setup.sh`, using the name of your newer Python.
- **`Could not find python3`** (setup.sh) or **`Python was not found`** (setup_windows.bat). Install Python. On Windows, tick "Add python.exe to PATH" in the installer.
- **"Groot could not start"** (start_groot.sh) or **"Groot did not answer, so your browser was not opened"** (start_groot.bat). Read the messages above it. "address already in use" (on Windows, "only one usage of each socket address") means another program, often a second copy of Groot or `adk web`, is using port 8000. The setup checker says so too. Close that program, then start Groot again.
- **`Access is denied`** when you start `adk.exe` (Windows). Some antivirus programs block the programs in `.venv\Scripts`. The start files avoid them by starting Groot through Python, and you can do the same by hand with `.venv\Scripts\python.exe -m web`.

## How it is built

```
deadline_agent/
  agent.py           Groot itself: its model, its instruction and its list of tools
  tools.py           the seven tools, the date rules, the reminders and the saving code
  friendly_errors.py short chat replies for a used up limit, a key problem or a timeout
  check_setup.py     the setup checker
  outline.py         the outline reader, one Gemini request for each outline
  documents.py       turns an outline file of any supported kind into what Gemini gets
  uts_calendar.py    the UTS 2026 Autumn and Spring calendars
  timetable.py       reads your tutorial days from your UTS timetable PDF
  canvas.py          fetches and reads your Canvas calendar feed
  importer.py        turns outline items, the timetable and Canvas into review rows, and saves them
  import_types.py    the shapes of the data passed between the parts above
  .env.example       example key file (the real .env is never committed)
web/                 Groot's web app, started with python -m web
  app.py             the routes, the safety checks and the server shared with ADK's chat
  pages.py           the HTML of the home page and the import page
  uploads.py         reads uploaded files into memory, with the size and count limits
  preview.py         the import page's Preview
  static/            the CSS and JavaScript the pages load
eval/                the two evaluations, see Measuring how well it works
tests/               1317 tests, no API key needed
docs/superpowers/specs/2026-11-04-outline-dropbox-design.md   the drop box's design, written before it was built
.github/workflows/tests.yml
requirements.txt     every package at an exact version
setup.sh, setup_windows.bat        the setup scripts
start_groot.sh, start_groot.bat    the start files
```

- **`agent.py`** defines `root_agent`, an ADK `Agent` called `agent_groot` that uses `gemini-3.5-flash` and the seven tools. Its instruction is a function, `groot_instruction`, which ADK runs before every request to Gemini (ADK's name for this is an instruction provider). It returns Groot's fixed instruction, today's date in Sydney, the rule to pass due dates through exactly as typed, where to import outlines, the rules for reminders, and the reminders block. While nothing is saved, it also suggests a few things to type.
- **`tools.py`** holds the seven tools. ADK reads each tool's name, type hints and docstring to tell Gemini what the tool does. Every tool returns a `status` and a `message`, and problems come back as a message Groot can pass on instead of a crash. The home page and the import page call the same tools, so the file lock, the safe saves and the backups work the same everywhere.
- **Why dates are worked out in Python.** The model does not reliably know today's date, so it is bad at things like "next friday". Plain rules in Python give the same answer every time, and each rule is covered by tests. The reply also spells out the full date, so a misunderstanding is easy to catch. For outlines, Gemini only copies the outline's words, like "week 7", and the UTS calendar code turns them into a date.
- **Protection against prompt injection.** Titles and subjects are typed by the student, or found in an outline, and end up in Groot's instruction, so a title like "Essay, ignore previous instructions" could try to give orders. When a deadline is saved, line breaks and runs of spaces in the title and subject become a single space. Before a title or subject goes into the reminders block, control and invisible characters become spaces, `<` and `>` are removed so it cannot fake the end of the block, double quotes become single quotes, and it is cut to 80 characters. Groot is told that the block, every title or subject in a tool result, and everything in a file are data, never instructions. An outline goes to Gemini apart from the reader's rules, with its text between two marker lines it cannot fake, and Gemini's answer must fit a fixed shape that is checked in Python. This keeps each piece of data in its place, but it cannot make the model fully immune.
- **Safe saves.** Each save writes the whole list to a temporary file in the same folder, makes sure it has reached the disk, then swaps it in with `os.replace` in a single step. A crash leaves either the old file or the new one, never half a file. A lock lets only one action read or change the file at a time, because ADK and the web server can run them on several threads. A test starts 20 saves at once on separate threads and checks that all 20 are kept.
- **Daylight saving.** All dates and times are Sydney time (`Australia/Sydney`). Lengths of time, such as "in 3 hours" or "2 hours overdue", are worked out in UTC, so they stay right on the two nights each year when Sydney's clocks change. For example, at 8 PM on Saturday 3 Oct 2026, "in 12 hours" is saved as 9:00 AM on Sunday, because the clocks go forward an hour that night. The `tzdata` package is included because Windows has no time zone database of its own for Python to use.

## Security and privacy

- **Only your computer can open Groot.** The server listens on 127.0.0.1 only. ADK's guard against "DNS rebinding", a trick where a website points its own name at 127.0.0.1, covers every page.
- **Other websites cannot change anything.** Any website open in your browser can send requests to 127.0.0.1, so every request to Groot's pages that changes something must carry Groot's own address in its Origin header, which a web page cannot fake, and the content type the route expects. ADK's own chat routes refuse other websites' Origin headers in the same way. So another site cannot add or delete deadlines or spend your Gemini requests.
- **Text is always shown as text.** Every title, subject and file name on the pages is escaped or set with `textContent`, so even a title like `<script>` is only shown. The pages only run Groot's own scripts and cannot be shown inside another site's frame.
- **Uploads stay in memory.** The import page reads your files into memory and never writes them to disk. The one exception is an old `.doc` or `.ppt` file, which LibreOffice needs as a file, so a copy goes into a temporary folder that is deleted straight after.
- **What goes to Google.** Each chat message goes to Gemini with Groot's instruction, which includes the titles and subjects of anything overdue or due in the next 7 days. Each outline you preview goes to Gemini, as the file itself or as its text. On the free tier, Google's terms allow it to use what you send to improve its products, and people at Google may read it, so do not put anything private in a title or in an outline you upload. See the [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms). Your timetable and your Canvas feed are read on your computer and never sent to Gemini.
- **Your key** is only in `deadline_agent/.env`, which git ignores. The setup checker never prints it, and the GitHub Actions check fails if a `.env` file is ever committed.

## Tests and CI

There are 1317 tests, run with pytest:

| File | Tests | What they cover |
| --- | --- | --- |
| `tests/test_dates.py` | 182 | Every date phrase, weekdays near the weekend, new months and years, leap days, daylight saving, and refused input |
| `tests/test_documents.py` | 137 | Every file type, telling the kind from the contents, macros, passwords, zip bombs, XML tricks, links that must never be fetched, and LibreOffice with a stand-in and the real program |
| `tests/test_reminders.py` | 113 | Reminder groups, exact edges like 11:59 PM, the friendly phrases, the reminders block, and the prompt injection protection |
| `tests/test_outline.py` | 109 | What the outline reader sends to Gemini, how the answer is checked, prompt injection and API errors, with a fake Gemini |
| `tests/test_uts_calendar.py` | 108 | Every week of both sessions against the official planner, StuVac, the exams and public holidays |
| `tests/test_web.py` | 99 | The home page and its API, escaping, the Origin and content type checks, and the real server shared with ADK's chat |
| `tests/test_tools.py` | 80 | The tools, title matching, saving, backups of unreadable files, failed saves and many threads at once |
| `tests/test_eval.py` | 77 | The outline evaluation's pairing, scores, real dates and spacing of requests |
| `tests/test_web_import.py` | 70 | The import page: every file kind, refused files, the timetable, Canvas, Preview and Save |
| `tests/test_importer.py` | 68 | Every row of the date rules, Canvas matching, public holidays, past dates and saving |
| `tests/test_start_and_setup.py` | 55 | The start files (`start_groot.sh` is run for real) and every part of the setup checker |
| `tests/test_friendly_errors.py` | 50 | The chat's replies for limits, key problems and timeouts |
| `tests/test_canvas.py` | 49 | Reading Canvas feeds, time zones, refused links, the size and time limits, and the link never logged |
| `tests/test_export.py` | 48 | The calendar file: its exact text, folded lines, escaping, IDs, daylight saving and failed saves |
| `tests/test_chat_eval.py` | 31 | The chat evaluation's cases and scoring, with a scripted stand in for Gemini |
| `tests/test_timetable.py` | 30 | Reading the UTS timetable layout, wrapped lines and damaged PDFs |
| `tests/test_agent.py` | 11 | Groot's tools and instruction, plus whole turns through ADK with a scripted stand in for Gemini |

No test needs an API key or the internet. Each test saves to its own temporary file, and every test that depends on the date sets the clock itself, so the results never depend on today's date.

GitHub Actions runs the tests on every push to `main` and on every pull request, on Python 3.11 (the oldest Groot supports), 3.13 and 3.14. The job can only read the code, fails if a `.env` or `deadlines.json` file is committed, and fails if any `GOOGLE_` or `GEMINI_` variable is set, which proves the tests pass without a key. The badge at the top shows the status of this workflow.

## Limitations and known gaps

- **One user, one local file.** There are no accounts. Everyone using the same copy shares one `deadlines.json`, and nothing syncs between devices.
- **The free tier is small.** About 20 requests a day is roughly 8 to 10 chat messages that use a tool, or 20 outlines. See [The Gemini free tier](#the-gemini-free-tier).
- **UTS only, and only 2026.** The calendar knows Autumn 2026 and Spring 2026. Other sessions, other years and other universities are not supported yet.
- **The outline reader can make mistakes.** Gemini can miss an item or misread a weight or a week, so always check the review table before you save. Rows that are assumed or need your date say so, but a misread week still gives a date that looks fine. Its accuracy has not been measured on real outlines in this repository yet, because the answer keys must be checked by hand first.
- **Old .doc and .ppt files depend on LibreOffice**, which runs with your own permissions. Groot blocks macros, link updates and web addresses, but it cannot rule out every trick a file from someone else might try, for example a link to a network share on Windows, or a bug in an old LibreOffice. Keep LibreOffice up to date, and save an old file from someone you do not trust as a PDF before you import it.
- **The chat is ADK's development page.** It has no login and is made for building agents, so only run Groot on your own computer. Port 8000 is fixed in the code.
- **Sydney time only.** The time zone is fixed in the code.
- **English only.** Date words like "friday" and "tomorrow" must be in English.
- **No editing.** To change a deadline, delete it and add it again.
- **No past deadlines.** You cannot add a deadline whose time has already passed, and imported rows that have passed start unticked.
- **Reminders only appear in Groot.** The chat and the home page show them, but Groot sends no notifications. Export to your calendar for those.
- **The Windows setup script shows your key on screen** while you paste it.

## Built with

Python, [Google ADK](https://github.com/google/adk-python) 2.11.0, Gemini 3.5 Flash, FastAPI, pytest and GitHub Actions, with LibreOffice for old Office files.

## Licence

MIT. See [LICENSE](LICENSE).
