# Chat evaluation results

Model, as reported by Gemini: gemini-3.5-flash-lite.

Cases scored: 69 of 69.

## Overall

| Check | Passed | Out of | Score |
| --- | --- | --- | --- |
| Whole cases (every check passed) | 68 | 69 | 99% |
| Right tool chosen | 64 | 64 | 100% |
| No tool call for an off-topic message | 5 | 5 | 100% |
| Due date passed exactly as typed | 39 | 39 | 100% |
| Saved deadlines correct | 39 | 40 | 98% |
| Nothing saved that should not be | 29 | 29 | 100% |

## By category

| Category | Passed | Out of | Score |
| --- | --- | --- | --- |
| add_dates | 18 | 19 | 95% |
| add_subject | 5 | 5 | 100% |
| strict_rules | 9 | 9 | 100% |
| list | 3 | 3 | 100% |
| next | 4 | 4 | 100% |
| reminders | 5 | 5 | 100% |
| mark_done | 5 | 5 | 100% |
| delete | 4 | 4 | 100% |
| off_topic | 5 | 5 | 100% |
| injection | 4 | 4 | 100% |
| edit | 6 | 6 | 100% |

## Failed cases

### date-20th-november

Category: add_dates. Failed: Saved deadlines correct.

Student (clock frozen at 2026-11-05 10:00): `Literature Review is due 20th november, add it please`

Tool calls made:
- `add_deadline(due_date='20th november', title='Literature Review', subject='Literature Review')` gave `{"status": "success", "message": "Saved 'Literature Review', due Friday 20 Nov 2026, 11:59 PM.", "deadline": {"title": "Literature Review", "due_date": "2026-11-20", "subject": "Literature Review", "d`

Tool calls expected:
- `add_deadline(title='Literature Review', due_date='20th november')`

Saved afterwards:
- `Literature Review`, due `2026-11-20`, subject `Literature Review`, not done

Expected saved:
- `Literature Review`, due `2026-11-20`, no subject, not done

Groot replied:

> Done! I've added your Literature Review for Friday, 20 November 2026.
