# How Groot was built: a timeline

This page follows Groot from its first commit to today: what was built and when, what went well, and what we fixed along the way. After the first version, every change went in as a pull request, so each step below links to the change itself. Dates are Sydney time, 2026.

## At a glance

- **First version:** 10 to 11 October. **Then 52 pull requests** between 3 and 25 November.
- **Automated tests:** 296 on 3 November, 1,457 on 5 November, 2,505 on 24 November and 2,789 on 25 November. They run on every change.
- **Measured with the real AI, not just claimed:** 68 of 69 realistic student messages handled correctly with Gemini 3.5 Flash-Lite, and 93% of the assessments in five real UTS outlines found, with no date silently wrong.

## 1. The first version (10 to 11 October)

I set up the project with Google's Agent Development Kit (ADK) and wrote the first Groot myself: an agent called Agent Groot, running on Gemini 3.5 Flash, with its personality and rules written in plain English. It stayed on the topic of deadlines, kept its replies short and friendly, and said honestly that it couldn't save anything yet instead of pretending to.

## 2. The core (3 to 4 November)

The basics a deadline tracker needs, with tests from the start.

- [#1](https://github.com/Richardyan701/deadline_tracker_agent/pull/1) Saving deadlines to a file, with tools to add, list, delete and mark them done, and to find the next one
- [#2](https://github.com/Richardyan701/deadline_tracker_agent/pull/2) Plain-English dates, like "next friday 5pm", "in 3 days" and "20 nov"
- [#3](https://github.com/Richardyan701/deadline_tracker_agent/pull/3) Reminders for deadlines that are overdue or due soon
- [#4](https://github.com/Richardyan701/deadline_tracker_agent/pull/4) Tests that run on GitHub for every change
- [#5](https://github.com/Richardyan701/deadline_tracker_agent/pull/5) A review pass: backups, safer saving, and dates that roll over into next year
- [#6](https://github.com/Richardyan701/deadline_tracker_agent/pull/6) A README and a setup that work on a fresh copy

## 3. Reading subject outlines (4 to 5 November)

The biggest step. Instead of typing in every deadline, a student drops in their subject outlines and Groot finds each assessment and its real date. The design was written down and reviewed first (#7), and a way to measure the reader's accuracy was built alongside it (#12).

- [#7](https://github.com/Richardyan701/deadline_tracker_agent/pull/7) The design for the outline drop box, reviewed before any code was written
- [#8](https://github.com/Richardyan701/deadline_tracker_agent/pull/8) The MIT licence
- [#9](https://github.com/Richardyan701/deadline_tracker_agent/pull/9) Exporting unfinished deadlines to a calendar file
- [#10](https://github.com/Richardyan701/deadline_tracker_agent/pull/10) A chat evaluation that scores how well Gemini uses Groot's tools
- [#11](https://github.com/Richardyan701/deadline_tracker_agent/pull/11) The UTS calendar, timetable and Canvas importer, which needs no AI
- [#12](https://github.com/Richardyan701/deadline_tracker_agent/pull/12) The outline reader, using Gemini, and the measurement of its accuracy
- [#13](https://github.com/Richardyan701/deadline_tracker_agent/pull/13) An easier start for new users: start files, a setup check and friendlier error messages
- [#14](https://github.com/Richardyan701/deadline_tracker_agent/pull/14) Web pages: a home page and the outline drop box
- [#15](https://github.com/Richardyan701/deadline_tracker_agent/pull/15) Outlines in many file types, not only PDF
- [#16](https://github.com/Richardyan701/deadline_tracker_agent/pull/16) Faster reading of .ods spreadsheets, and an install that works on Python 3.10
- [#17](https://github.com/Richardyan701/deadline_tracker_agent/pull/17) A final review: every outline format, one way to start Groot, and scoring against real dates
- [#18](https://github.com/Richardyan701/deadline_tracker_agent/pull/18) Warnings when deadlines clash, and a "What do I need?" grade calculator
- [#19](https://github.com/Richardyan701/deadline_tracker_agent/pull/19), [#20](https://github.com/Richardyan701/deadline_tracker_agent/pull/20) and [#21](https://github.com/Richardyan701/deadline_tracker_agent/pull/21) Three fixes, explained under [What we fixed along the way](#what-we-fixed-along-the-way)

## 4. Results and polish (7 to 13 November)

- [#22](https://github.com/Richardyan701/deadline_tracker_agent/pull/22) The outline accuracy results in the README
- [#23](https://github.com/Richardyan701/deadline_tracker_agent/pull/23) A README that's easier for a first-time visitor
- [#24](https://github.com/Richardyan701/deadline_tracker_agent/pull/24) The final chat evaluation: all 63 cases passed
- [#25](https://github.com/Richardyan701/deadline_tracker_agent/pull/25) A shorter README, with the detail moved to the [reference](reference.md)
- [#26](https://github.com/Richardyan701/deadline_tracker_agent/pull/26) "Why does Groot feel similar to Notion?"
- [#27](https://github.com/Richardyan701/deadline_tracker_agent/pull/27) Editing a deadline, in the chat or with an Edit button
- [#28](https://github.com/Richardyan701/deadline_tracker_agent/pull/28) Proofreading of comments, docs and messages
- [#29](https://github.com/Richardyan701/deadline_tracker_agent/pull/29) Two out-of-date facts fixed in the chat evaluation's notes

Then I paused for exams.

## 5. My own feedback, after exams (16 to 19 November)

After exams I wrote down what I wanted Groot to do better: more universities, safer handling of personal details, a choice of AI model, and a way around Gemini's small free limit. Then we worked through it.

- [#30](https://github.com/Richardyan701/deadline_tracker_agent/pull/30) UNSW, USyd and Macquarie, with their 2027 calendars
- [#31](https://github.com/Richardyan701/deadline_tracker_agent/pull/31) A check that holds back sensitive details, like card numbers, passwords and student IDs, before anything is sent or saved
- [#32](https://github.com/Richardyan701/deadline_tracker_agent/pull/32) Another Gemini model with one line in `.env`
- [#33](https://github.com/Richardyan701/deadline_tracker_agent/pull/33) Models from other companies
- [#34](https://github.com/Richardyan701/deadline_tracker_agent/pull/34) The README's newer sections in plainer words
- [#35](https://github.com/Richardyan701/deadline_tracker_agent/pull/35) Any university: a student types in their own session's dates
- [#36](https://github.com/Richardyan701/deadline_tracker_agent/pull/36) A made-up sample outline to try the import with
- [#37](https://github.com/Richardyan701/deadline_tracker_agent/pull/37) When Gemini is busy, a backup model takes over
- [#38](https://github.com/Richardyan701/deadline_tracker_agent/pull/38) Setup asks which Gemini model to use
- [#39](https://github.com/Richardyan701/deadline_tracker_agent/pull/39) Six editing cases added to the chat evaluation
- [#40](https://github.com/Richardyan701/deadline_tracker_agent/pull/40) A demo GIF and a "How this was built" section
- [#41](https://github.com/Richardyan701/deadline_tracker_agent/pull/41) The demo redone as a real recording, with a visible cursor
- [#42](https://github.com/Richardyan701/deadline_tracker_agent/pull/42) The introduction moved to the top, with exact credit wording

## 6. Reaching more students (24 to 25 November)

- [#43](https://github.com/Richardyan701/deadline_tracker_agent/pull/43) A better backup order, from a week of hourly checks on Gemini
- [#44](https://github.com/Richardyan701/deadline_tracker_agent/pull/44) Singapore time as well as Sydney time
- [#45](https://github.com/Richardyan701/deadline_tracker_agent/pull/45) NUS, NTU and SMU, with their 2027 calendars and Singapore's public holidays
- [#46](https://github.com/Richardyan701/deadline_tracker_agent/pull/46) Week-number dates, like "friday week 7 5pm"
- [#47](https://github.com/Richardyan701/deadline_tracker_agent/pull/47) A tip about UTS's 3-day short extensions
- [#48](https://github.com/Richardyan701/deadline_tracker_agent/pull/48) Groot's website: the home page in your own browser, with nothing to install
- [#49](https://github.com/Richardyan701/deadline_tracker_agent/pull/49) The current 2026 semesters for all seven universities
- [#50](https://github.com/Richardyan701/deadline_tracker_agent/pull/50) Reminder times, adding many deadlines at once, a sample semester to try, and shorter text
- [#51](https://github.com/Richardyan701/deadline_tracker_agent/pull/51) Plainer wording for calendar reminders
- [#52](https://github.com/Richardyan701/deadline_tracker_agent/pull/52) The final counts from the week of hourly checks

## What went well

- **Measuring instead of guessing.** Each part that uses AI has its own test with real examples: realistic student messages, real subject outlines, and a week of hourly checks on Gemini to choose the backup order.
- **Checking facts at the source.** The university calendars come from each university's official dates. The outline reader was tried on real outlines from UTS, UNSW, USyd and Macquarie, and the UTS extension tip follows UTS's own page.
- **Privacy from the start.** Saved deadlines stay on your computer, or in your own browser on the website. Groot holds no one's data and costs nothing to run.
- **Small, tested steps.** Every change was its own pull request, and it had to pass the automated tests on three versions of Python before I approved it.

## What we fixed along the way

- **An honest privacy note ([#20](https://github.com/Richardyan701/deadline_tracker_agent/pull/20)).** Early on, Groot said your data stays on your laptop. That was true for saved deadlines, but chat messages and previewed outlines go to Google's Gemini, which may use them on the free tier. The README and the pages now say so plainly, and list what never to type.
- **A test that was fooling itself ([#19](https://github.com/Richardyan701/deadline_tracker_agent/pull/19)).** When the free daily limit ran out overnight, Groot's polite "limit used up" replies were scored as real answers. The chat test looked finished, with most cases wrongly marked as failures. Now a limit error stops the test, and the bad results were thrown away and run again.
- **A test that failed for the wrong reason ([#21](https://github.com/Richardyan701/deadline_tracker_agent/pull/21)).** On GitHub's Python 3.14 runner, one test sometimes failed because a test server from the test before was still closing. The check now handles that, so the test no longer fails for a reason that has nothing to do with Groot.
- **Gemini's small free limit.** Gemini 3.5 Flash allows only about 20 requests a day for free, and Google often answers "high demand". Setup now recommends Flash-Lite, which allows at least six times as many. A busy model hands its work to a backup ([#37](https://github.com/Richardyan701/deadline_tracker_agent/pull/37)), and the backup order comes from a week of hourly checks ([#43](https://github.com/Richardyan701/deadline_tracker_agent/pull/43), [#52](https://github.com/Richardyan701/deadline_tracker_agent/pull/52)).
- **Too much to read.** The README and the home page were long. The README was shortened, with the detail moved to a reference page ([#23](https://github.com/Richardyan701/deadline_tracker_agent/pull/23), [#25](https://github.com/Richardyan701/deadline_tracker_agent/pull/25), [#34](https://github.com/Richardyan701/deadline_tracker_agent/pull/34)), and the home page text was cut down ([#50](https://github.com/Richardyan701/deadline_tracker_agent/pull/50), [#51](https://github.com/Richardyan701/deadline_tracker_agent/pull/51)).
- **Only for UTS.** Groot now knows four Australian and three Singapore universities, and works at any other university too ([#30](https://github.com/Richardyan701/deadline_tracker_agent/pull/30), [#35](https://github.com/Richardyan701/deadline_tracker_agent/pull/35), [#45](https://github.com/Richardyan701/deadline_tracker_agent/pull/45), [#49](https://github.com/Richardyan701/deadline_tracker_agent/pull/49)).
- **Laptop only.** Friends can now open the website, with nothing to install ([#48](https://github.com/Richardyan701/deadline_tracker_agent/pull/48)).
- **One deadline at a time.** A whole list can now be pasted in at once ([#50](https://github.com/Richardyan701/deadline_tracker_agent/pull/50)).

## Tried, and decided against

- **Groq for chatting.** Its free tier allows plenty of requests a day but only 8,000 tokens a minute. Each Groot request is about 3,000 tokens, so it managed about one message a minute. It's still fine for reading outlines one at a time.
- **Tailscale for phones.** It would have meant one more app and one more company holding account details. So the phone version became the website instead, which stores nothing.

## Next on the list

- A calendar or week view, with a colour for each subject
- A clearer name for the "Week numbers count in" setting
- Hiding the Grades section for Singapore students, where it doesn't apply
- Tags for assessment types, like essay, quiz or exam
- Outline import and the chat on the website
