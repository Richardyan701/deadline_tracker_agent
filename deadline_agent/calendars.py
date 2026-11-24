"""The official university calendars, used to turn "week 7" into a real date.

Outlines give due dates as teaching weeks, like "due in week 7". Teaching
weeks are not evenly spaced, because most sessions have a break in the middle
that has no week number. So the dates come from the official calendars below,
never from counting weeks.

Seven universities are built in: four in Sydney (UTS, UNSW, the University
of Sydney and Macquarie University) and three in Singapore (NUS, NTU and
SMU). Each one counts its weeks differently:

    UTS         12 teaching weeks. The StuVac week in the middle has no number.
    UNSW        10 weeks in a term, all in a row. Week 6 is "flexibility week",
                which keeps its number even though most classes do not run.
    USyd        13 teaching weeks. The mid-semester break has no number.
    Macquarie   13 teaching weeks. The two-week mid-session recess has no number.
    NUS         13 teaching weeks. Recess week (after week 6) and reading week
                (before the exams) have no number.
    NTU         13 teaching weeks. Recess week (after week 7) has no number.
    SMU         Weeks 1 to 14 in a row, with week 8 as recess week, which keeps
                its number, so 13 of them are teaching weeks.

Weeks start on Monday. Dates are plain local dates and times (Sydney's for the
Australian universities, Singapore's for the Singaporean ones) with no
timezone attached, the same as the saved due dates in tools.py.

THE CALENDARS RUN OUT. Every university publishes new dates each year, so
the next year's sessions must be added here by hand from the official pages
below. open_sessions() leaves out the sessions that have finished, and
finished_universities() says which universities have nothing left, so the
drop box can say so instead of giving wrong dates.

Where the dates come from (each one was checked against a second source, the
Universities Australia "Academic calendar 2026-27" table):

    UTS 2026    the UTS "2026 Assessment Planners" (Main calendar)
                https://drupal.uts.edu.au/sites/default/files/article/downloads/2026AssessmentPlanners_CalendarMain.pdf
    UTS 2027    https://www.uts.edu.au/for-students/current-students/managing-your-course/important-dates/academic-year-dates/2027-academic-year-dates
    UNSW 2027   https://www.unsw.edu.au/student/managing-your-studies/key-dates/academic-calendar
    UNSW 2026   the 2026 Term 3 table on the same page
    USyd 2026   the "Student wall calendar 2026" on the same page as 2027, and the
                Semester 2 STUVAC and exam dates on
                https://www.sydney.edu.au/students/exams-assessments/exams/dates.html
    Macquarie 2026
                classes and recess from Universities Australia's 2026 summary and
                Macquarie's 2026 holiday letter (recess 21 Sep to 5 Oct), and the exam
                period on https://iexams.mq.edu.au/
    USyd 2027   the "Student wall calendar 2027" on https://www.sydney.edu.au/students/key-dates.html
    Macquarie 2027
                the Session 1 and Session 2 table on https://students.mq.edu.au/study/course/dates
                (classes start, mid-session break, classes resume, classes end and exams)
    Second source for all four
                https://universitiesaustralia.edu.au/our-universities/teaching-calendars/
    NUS         https://nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf
                https://nus.edu.sg/registrar/docs/default-source/calendar/ay2027-2028.pdf
    NTU         https://www.ntu.edu.sg/admissions/matriculation/academic-calendars, the
                AY2026-27 semester calendar and the AY2027-28 one, which NTU marks as
                "indicative", so its dates may still change
    SMU         https://www.smu.edu.sg/sites/default/files/courses/calendars/ug-jd/2026-2027.pdf
                https://www.smu.edu.sg/sites/default/files/courses/calendars/ug-jd/2027-2028.pdf
                (the undergraduate and Juris Doctor calendars)
    Each Singapore date was read from the university's own PDF and agrees with
    what third-party summaries (for example NTUMods) say where they cover it.

Only each university's main calendar is here. Other calendars (UTS Health,
UNSW Canberra, summer and winter terms, intensive units and so on) are not.
"""

import re
from datetime import date, datetime, timedelta

from .tools import WEEKDAY_NAMES

# The universities Groot knows, in the order the drop box lists them.
# "name" is the short name used in sentences, "full_name" is for the picker,
# and "country" is a key of region.COUNTRIES (and of HOLIDAYS below).
UNIVERSITIES = {
    "uts": {"name": "UTS", "full_name": "University of Technology Sydney (UTS)", "country": "AU"},
    "unsw": {"name": "UNSW", "full_name": "UNSW Sydney", "country": "AU"},
    "usyd": {"name": "USyd", "full_name": "University of Sydney", "country": "AU"},
    "mq": {"name": "Macquarie", "full_name": "Macquarie University", "country": "AU"},
    "nus": {"name": "NUS", "full_name": "National University of Singapore (NUS)", "country": "SG"},
    "ntu": {"name": "NTU", "full_name": "Nanyang Technological University (NTU)", "country": "SG"},
    "smu": {"name": "SMU", "full_name": "Singapore Management University (SMU)", "country": "SG"},
}


def _mondays(first: date, count: int) -> list[date]:
    """count Mondays in a row, one week apart, starting at first."""
    return [first + timedelta(weeks=i) for i in range(count)]


# Every session Groot knows. Each one has:
#   "university"   a key of UNIVERSITIES
#   "name"         what the university calls it, like "Spring 2026" or "Term 1 2027"
#   "weeks"        the Monday of each teaching week, week 1 first
#   "breaks"       the Monday of each week between week 1 and the exams that has no week number
#   "exams"        the first and last day of the exam period
#   "quiet_weeks"  (UNSW and SMU) numbered weeks when most classes do not run, with what they are called
#   "exam_weeks"   (only SMU) the week numbers the calendar gives its exam weeks
SESSIONS = {
    # ---------- UTS: 12 teaching weeks, with StuVac after week 7 or 8 ----------
    "AUT2026": {
        "university": "uts",
        "name": "Autumn 2026",
        # Weeks 1 to 7 start on 16 Feb. After StuVac, weeks 8 to 12 start on 13 Apr.
        "weeks": _mondays(date(2026, 2, 16), 7) + _mondays(date(2026, 4, 13), 5),
        # The Mondays of the two StuVac weeks: 6 to 12 Apr and 18 to 24 May
        "breaks": [date(2026, 4, 6), date(2026, 5, 18)],
        "exams": (date(2026, 5, 25), date(2026, 6, 12)),
    },
    "SPR2026": {
        "university": "uts",
        "name": "Spring 2026",
        # Weeks 1 to 8 start on 27 Jul. After StuVac, weeks 9 to 12 start on 28 Sep.
        "weeks": _mondays(date(2026, 7, 27), 8) + _mondays(date(2026, 9, 28), 4),
        # The Mondays of the two StuVac weeks: 21 to 27 Sep and 26 Oct to 1 Nov
        "breaks": [date(2026, 9, 21), date(2026, 10, 26)],
        "exams": (date(2026, 11, 2), date(2026, 11, 20)),
    },
    "AUT2027": {
        "university": "uts",
        "name": "Autumn 2027",
        # Session starts Mon 15 Feb. Mid-session StuVac is 12 to 16 Apr, and formal classes end Fri 14 May.
        # So weeks 1 to 8 start on 15 Feb and weeks 9 to 12 start on 19 Apr.
        "weeks": _mondays(date(2027, 2, 15), 8) + _mondays(date(2027, 4, 19), 4),
        # Mid-session StuVac 12 to 16 Apr and final StuVac 17 to 21 May
        "breaks": [date(2027, 4, 12), date(2027, 5, 17)],
        # Final assessment period: Mon 24 May to Fri 11 Jun
        "exams": (date(2027, 5, 24), date(2027, 6, 11)),
    },
    "SPR2027": {
        "university": "uts",
        "name": "Spring 2027",
        # Session starts Mon 26 Jul. Mid-session StuVac is 20 to 24 Sep, and formal classes end Fri 22 Oct.
        # So weeks 1 to 8 start on 26 Jul and weeks 9 to 12 start on 27 Sep.
        "weeks": _mondays(date(2027, 7, 26), 8) + _mondays(date(2027, 9, 27), 4),
        # Mid-session StuVac 20 to 24 Sep and final StuVac 25 to 29 Oct
        "breaks": [date(2027, 9, 20), date(2027, 10, 25)],
        # Final assessment period: Mon 1 Nov to Fri 19 Nov
        "exams": (date(2027, 11, 1), date(2027, 11, 19)),
    },
    # ---------- UNSW: 10 weeks in a row, and week 6 is flexibility week ----------
    # UNSW changes to two 12-week semesters in 2028, so the 2028 sessions will look different.
    "UNSW_T3_2026": {
        "university": "unsw",
        "name": "Term 3 2026",
        # From UNSW's academic calendar: teaching period T3 14 Sep to 20 Nov, flexibility week 19 to 25 Oct
        "weeks": _mondays(date(2026, 9, 14), 10),
        # Study period T3: 21 to 26 Nov
        "breaks": [date(2026, 11, 23)],
        # Exams T3: 27 Nov to 10 Dec
        "exams": (date(2026, 11, 27), date(2026, 12, 10)),
        "quiet_weeks": {6: "flexibility week"},
    },
    "UNSW_T1_2027": {
        "university": "unsw",
        "name": "Term 1 2027",
        # Teaching period T1: 15 Feb to 23 Apr. Flexibility week: 22 to 28 Mar.
        "weeks": _mondays(date(2027, 2, 15), 10),
        # Study period T1: 24 to 29 Apr, the week between week 10 and the exams
        "breaks": [date(2027, 4, 26)],
        # Exams T1: 30 Apr to 13 May
        "exams": (date(2027, 4, 30), date(2027, 5, 13)),
        "quiet_weeks": {6: "flexibility week"},
    },
    "UNSW_T2_2027": {
        "university": "unsw",
        "name": "Term 2 2027",
        # Teaching period T2: 31 May to 6 Aug. Flexibility week: 5 to 11 Jul.
        "weeks": _mondays(date(2027, 5, 31), 10),
        # Study period T2: 7 to 12 Aug
        "breaks": [date(2027, 8, 9)],
        # Exams T2: 13 to 26 Aug
        "exams": (date(2027, 8, 13), date(2027, 8, 26)),
        "quiet_weeks": {6: "flexibility week"},
    },
    "UNSW_T3_2027": {
        "university": "unsw",
        "name": "Term 3 2027",
        # Teaching period T3: 13 Sep to 19 Nov. Flexibility week: 18 to 24 Oct.
        "weeks": _mondays(date(2027, 9, 13), 10),
        # Study period T3: 20 to 25 Nov
        "breaks": [date(2027, 11, 22)],
        # Exams T3: 26 Nov to 9 Dec
        "exams": (date(2027, 11, 26), date(2027, 12, 9)),
        "quiet_weeks": {6: "flexibility week"},
    },
    # ---------- USyd: 13 teaching weeks, with a one-week mid-semester break ----------
    "USYD_S2_2026": {
        "university": "usyd",
        "name": "Semester 2 2026",
        # From USyd's 2026 student wall calendar: teaching weeks 3 Aug to 8 Nov, mid-semester break
        # 28 Sep to 5 Oct, where Mon 5 Oct is the Labour Day holiday. The calendar numbers weeks 1 to 8
        # from 3 Aug and weeks 9 to 13 from 5 Oct.
        "weeks": _mondays(date(2026, 8, 3), 8) + _mondays(date(2026, 10, 5), 5),
        # The mid-semester break, then STUVAC 9 to 15 Nov
        "breaks": [date(2026, 9, 28), date(2026, 11, 9)],
        # Examinations: 16 to 28 Nov (also on USyd's exam dates page)
        "exams": (date(2026, 11, 16), date(2026, 11, 28)),
    },
    "USYD_S1_2027": {
        "university": "usyd",
        "name": "Semester 1 2027",
        # Teaching weeks: 22 Feb to 30 May. Mid-semester break: 29 Mar to 4 Apr.
        # So weeks 1 to 5 start on 22 Feb and weeks 6 to 13 start on 5 Apr.
        "weeks": _mondays(date(2027, 2, 22), 5) + _mondays(date(2027, 4, 5), 8),
        # The mid-semester break, then STUVAC 31 May to 6 Jun
        "breaks": [date(2027, 3, 29), date(2027, 5, 31)],
        # Examinations: 7 to 19 Jun
        "exams": (date(2027, 6, 7), date(2027, 6, 19)),
    },
    "USYD_S2_2027": {
        "university": "usyd",
        "name": "Semester 2 2027",
        # Teaching weeks: 2 Aug to 7 Nov. Mid-semester break: 27 Sep to 4 Oct, where
        # Mon 4 Oct is the Labour Day holiday. So weeks 1 to 8 start on 2 Aug and
        # weeks 9 to 13 start on 4 Oct, with classes back on Tue 5 Oct.
        "weeks": _mondays(date(2027, 8, 2), 8) + _mondays(date(2027, 10, 4), 5),
        # The mid-semester break, then STUVAC 8 to 14 Nov
        "breaks": [date(2027, 9, 27), date(2027, 11, 8)],
        # Examinations: 15 to 27 Nov
        "exams": (date(2027, 11, 15), date(2027, 11, 27)),
    },
    # ---------- Macquarie: 13 teaching weeks, with a two-week mid-session recess ----------
    "MQ_S2_2026": {
        "university": "mq",
        "name": "Session 2 2026",
        # Classes 27 Jul to 8 Nov (Universities Australia's 2026 summary). Session 2 recess 21 Sep to
        # 5 Oct (Macquarie's 2026 holiday letter), where Mon 5 Oct is the Labour Day holiday.
        # So weeks 1 to 8 start on 27 Jul and weeks 9 to 13 start on 5 Oct.
        "weeks": _mondays(date(2026, 7, 27), 8) + _mondays(date(2026, 10, 5), 5),
        "breaks": [date(2026, 9, 21), date(2026, 9, 28)],
        # Session 2 2026 exam period: 9 to 27 Nov (iexams.mq.edu.au)
        "exams": (date(2026, 11, 9), date(2026, 11, 27)),
    },
    "MQ_S1_2027": {
        "university": "mq",
        "name": "Session 1 2027",
        # Classes: 22 Feb to 6 Jun. Mid-session break: 12 to 25 Apr. Classes resume on
        # Tue 27 Apr, because Mon 26 Apr is the extra Anzac Day holiday.
        # So weeks 1 to 7 start on 22 Feb and weeks 8 to 13 start on 26 Apr.
        "weeks": _mondays(date(2027, 2, 22), 7) + _mondays(date(2027, 4, 26), 6),
        "breaks": [date(2027, 4, 12), date(2027, 4, 19)],
        # Exams: 7 to 25 Jun
        "exams": (date(2027, 6, 7), date(2027, 6, 25)),
    },
    "MQ_S2_2027": {
        "university": "mq",
        "name": "Session 2 2027",
        # Classes: 26 Jul to 7 Nov. Mid-session break: 20 Sep to 4 Oct, where Mon 4 Oct
        # is the Labour Day holiday. So weeks 1 to 8 start on 26 Jul and weeks 9 to 13
        # start on 4 Oct, with classes resuming on Tue 5 Oct.
        "weeks": _mondays(date(2027, 7, 26), 8) + _mondays(date(2027, 10, 4), 5),
        "breaks": [date(2027, 9, 20), date(2027, 9, 27)],
        # Exams: 8 to 26 Nov
        "exams": (date(2027, 11, 8), date(2027, 11, 26)),
    },
    # ---------- NUS: 13 teaching weeks; recess week and reading week have no number ----------
    "NUS_AY2627_S1": {
        "university": "nus",
        "name": "AY2026/27 Semester 1 (Aug to Dec 2026)",
        # Weeks 1 to 6 start on Mon 10 Aug. Recess week is Sat 19 to Sun 27 Sep.
        # Weeks 7 to 13 start on Mon 28 Sep. Reading week is Sat 14 to Fri 20 Nov.
        "weeks": _mondays(date(2026, 8, 10), 6) + _mondays(date(2026, 9, 28), 7),
        "breaks": [date(2026, 9, 21), date(2026, 11, 16)],
        # Examination: Sat 21 Nov to Sat 5 Dec
        "exams": (date(2026, 11, 21), date(2026, 12, 5)),
    },
    "NUS_AY2627_S2": {
        "university": "nus",
        "name": "AY2026/27 Semester 2 (Jan to May 2027)",
        # Weeks 1 to 6 start on Mon 11 Jan. Recess week is Sat 20 to Sun 28 Feb.
        # Weeks 7 to 13 start on Mon 1 Mar. Reading week is Sat 17 to Fri 23 Apr.
        "weeks": _mondays(date(2027, 1, 11), 6) + _mondays(date(2027, 3, 1), 7),
        "breaks": [date(2027, 2, 22), date(2027, 4, 19)],
        # Examination: Sat 24 Apr to Sat 8 May
        "exams": (date(2027, 4, 24), date(2027, 5, 8)),
    },
    "NUS_AY2728_S1": {
        "university": "nus",
        "name": "AY2027/28 Semester 1 (Aug to Dec 2027)",
        # Weeks 1 to 6 start on Mon 9 Aug. Recess week is Sat 18 to Sun 26 Sep.
        # Weeks 7 to 13 start on Mon 27 Sep. Reading week is Sat 13 to Fri 19 Nov.
        "weeks": _mondays(date(2027, 8, 9), 6) + _mondays(date(2027, 9, 27), 7),
        "breaks": [date(2027, 9, 20), date(2027, 11, 15)],
        # Examination: Sat 20 Nov to Sat 4 Dec
        "exams": (date(2027, 11, 20), date(2027, 12, 4)),
    },
    # ---------- NTU: 13 teaching weeks; recess week (after week 7) has no number ----------
    "NTU_AY2627_S1": {
        "university": "ntu",
        "name": "AY2026/27 Semester 1 (Aug to Dec 2026)",
        # Teaching weeks 1 to 7 start on Mon 10 Aug. Recess week is Mon 28 Sep to Fri 2 Oct.
        # Teaching weeks 8 to 13 start on Mon 5 Oct.
        "weeks": _mondays(date(2026, 8, 10), 7) + _mondays(date(2026, 10, 5), 6),
        "breaks": [date(2026, 9, 28)],
        # Revision and examination weeks: Mon 16 Nov to Fri 4 Dec
        "exams": (date(2026, 11, 16), date(2026, 12, 4)),
    },
    "NTU_AY2627_S2": {
        "university": "ntu",
        "name": "AY2026/27 Semester 2 (Jan to May 2027)",
        # Teaching weeks 1 to 7 start on Mon 11 Jan. Recess week is Mon 1 to Fri 5 Mar.
        # Teaching weeks 8 to 13 start on Mon 8 Mar, and week 13 ends on Fri 16 Apr.
        "weeks": _mondays(date(2027, 1, 11), 7) + _mondays(date(2027, 3, 8), 6),
        "breaks": [date(2027, 3, 1)],
        # Revision and examination weeks: Mon 19 Apr to Fri 7 May (NTU's calendar does not separate them)
        "exams": (date(2027, 4, 19), date(2027, 5, 7)),
    },
    "NTU_AY2728_S1": {
        "university": "ntu",
        "name": "AY2027/28 Semester 1 (Aug to Dec 2027, indicative)",
        # NTU marks this calendar "indicative": its dates may still change.
        # Teaching weeks 1 to 7 start on Mon 9 Aug. Recess week is Mon 27 Sep to Fri 1 Oct.
        # Teaching weeks 8 to 13 start on Mon 4 Oct.
        "weeks": _mondays(date(2027, 8, 9), 7) + _mondays(date(2027, 10, 4), 6),
        "breaks": [date(2027, 9, 27)],
        # Revision and examination weeks: Mon 15 Nov to Fri 3 Dec
        "exams": (date(2027, 11, 15), date(2027, 12, 3)),
    },
    # ---------- SMU: weeks 1 to 14 in a row; week 8 is recess week and keeps its number ----------
    "SMU_AY2627_T1": {
        "university": "smu",
        "name": "AY2026/27 Term 1 (Aug to Dec 2026)",
        # Weeks 1 to 14 start on Mon 17 Aug. Week 8 (Mon 5 to Sun 11 Oct) is recess week.
        "weeks": _mondays(date(2026, 8, 17), 14),
        "breaks": [],
        # Examination (weeks 15 and 16): Mon 23 Nov to Sun 6 Dec
        "exams": (date(2026, 11, 23), date(2026, 12, 6)),
        "quiet_weeks": {8: "recess week"},
        "exam_weeks": (15, 16),
    },
    "SMU_AY2627_T2": {
        "university": "smu",
        "name": "AY2026/27 Term 2 (Jan to May 2027)",
        # Weeks 1 to 14 start on Mon 11 Jan. Week 8 (Mon 1 to Sun 7 Mar) is recess week.
        "weeks": _mondays(date(2027, 1, 11), 14),
        "breaks": [],
        # Examination (weeks 15 and 16): Mon 19 Apr to Sun 2 May
        "exams": (date(2027, 4, 19), date(2027, 5, 2)),
        "quiet_weeks": {8: "recess week"},
        "exam_weeks": (15, 16),  # SMU's calendar numbers its two exam weeks
    },
    "SMU_AY2728_T1": {
        "university": "smu",
        "name": "AY2027/28 Term 1 (Aug to Dec 2027)",
        # Weeks 1 to 14 start on Mon 16 Aug. Week 8 (Mon 4 to Sun 10 Oct) is recess week.
        "weeks": _mondays(date(2027, 8, 16), 14),
        "breaks": [],
        # Examination (weeks 15 and 16): Mon 22 Nov to Sun 5 Dec
        "exams": (date(2027, 11, 22), date(2027, 12, 5)),
        "quiet_weeks": {8: "recess week"},
        "exam_weeks": (15, 16),
    },
}

# Every NSW public holiday in 2026 and 2027, for the Australian universities, which are all in Sydney.
# Source: the NSW Government list at https://www.nsw.gov.au/about-nsw/public-holidays
# The extra Monday after Anzac Day 2026 was announced on 15 Feb 2026:
# https://www.nsw.gov.au/ministerial-releases/minns-labor-government-announces-extra-public-holiday-year
# Left out on purpose: the Bank Holiday on the first Monday of August, which
# is only for banks, so it is not a public holiday for everyone.
PUBLIC_HOLIDAYS = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 26): "Australia Day",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 4): "Easter Saturday",
    date(2026, 4, 5): "Easter Sunday",
    date(2026, 4, 6): "Easter Monday",
    date(2026, 4, 25): "Anzac Day",
    date(2026, 4, 27): "the extra Anzac Day holiday",
    date(2026, 6, 8): "the King's Birthday",
    date(2026, 10, 5): "Labour Day",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 26): "Boxing Day",
    date(2026, 12, 28): "the extra Boxing Day holiday",
    date(2027, 1, 1): "New Year's Day",
    date(2027, 1, 26): "Australia Day",
    date(2027, 3, 26): "Good Friday",
    date(2027, 3, 27): "Easter Saturday",
    date(2027, 3, 28): "Easter Sunday",
    date(2027, 3, 29): "Easter Monday",
    date(2027, 4, 25): "Anzac Day",
    date(2027, 4, 26): "the extra Anzac Day holiday",
    date(2027, 6, 14): "the King's Birthday",
    date(2027, 10, 4): "Labour Day",
    date(2027, 12, 25): "Christmas Day",
    date(2027, 12, 26): "Boxing Day",
    date(2027, 12, 27): "the extra Christmas Day holiday",
    date(2027, 12, 28): "the extra Boxing Day holiday",
}

# Every Singapore public holiday from August 2026 to the end of 2027, for the Singaporean
# universities. The earliest session here starts in August 2026, so earlier 2026 holidays are left out.
# 2026: the holiday lists printed on the NUS and NTU AY2026/27 calendars, which also say that
# when a holiday falls on a Sunday, the Monday after it is a holiday too.
# 2027: the Ministry of Manpower's official list, as published on the government's
# open data site: https://data.gov.sg/datasets/d_0ba69fc6d56717ff0bf8083c6af3bb84/view
# and https://www.mom.gov.sg/newsroom/press-releases/2026/0618-public-holidays-for-2027
# The Hari Raya dates depend on sighting the moon, so MOM may move them.
SINGAPORE_HOLIDAYS = {
    date(2026, 8, 9): "National Day",
    date(2026, 8, 10): "the National Day holiday in lieu",  # 9 Aug 2026 is a Sunday
    date(2026, 11, 8): "Deepavali",
    date(2026, 11, 9): "the Deepavali holiday in lieu",  # 8 Nov 2026 is a Sunday
    date(2026, 12, 25): "Christmas Day",
    date(2027, 1, 1): "New Year's Day",
    date(2027, 2, 6): "Chinese New Year",
    date(2027, 2, 7): "Chinese New Year",
    date(2027, 2, 8): "the Chinese New Year holiday in lieu",  # day 2 falls on a Sunday
    date(2027, 3, 10): "Hari Raya Puasa",
    date(2027, 3, 26): "Good Friday",
    date(2027, 5, 1): "Labour Day",
    date(2027, 5, 17): "Hari Raya Haji",
    date(2027, 5, 20): "Vesak Day",
    date(2027, 8, 9): "National Day",
    date(2027, 10, 28): "Deepavali",
    date(2027, 12, 25): "Christmas Day",
}

# Which holidays apply to a university in each country, and what the notes call them
HOLIDAYS = {"AU": ("NSW", PUBLIC_HOLIDAYS), "SG": ("Singapore", SINGAPORE_HOLIDAYS)}


# ---------- a session the student describes themselves ----------
#
# A student at any other university can tell Groot their own calendar: when
# week 1 starts, how many teaching weeks there are, and where the break with
# no week number falls. The drop box packs that into one session code, like
#
#     CUSTOM:2027-03-01:12:6:1
#
# which means week 1 starts in the week of 1 March 2027, there are 12 teaching
# weeks, and a 1-week break comes after week 6. "0" for the last two parts
# means no break. Everything else then works the same as a built-in session.

CUSTOM_PREFIX = "CUSTOM:"
CUSTOM_CODE = re.compile(r"CUSTOM:([0-9]{4}-[0-9]{2}-[0-9]{2}):([0-9]{1,2}):([0-9]{1,2}):([0-9])")
MAX_CUSTOM_WEEKS = 20  # the longest session Groot accepts
MAX_BREAK_WEEKS = 4


def custom_code(week_1: date, weeks: int, break_after: int = 0, break_weeks: int = 0) -> str:
    """The session code for a calendar the student describes. custom_session explains the parts."""
    return f"{CUSTOM_PREFIX}{week_1.isoformat()}:{weeks}:{break_after}:{break_weeks}"


def custom_session(code: str) -> dict:
    """The calendar for a "CUSTOM:..." session code, in the same shape as the built-in sessions.

    Week 1 starts on the Monday of the week the given date is in. A break
    after week N pushes every later week back by the length of the break.
    The exam period is not known, so "exams" is None.
    Raises ValueError if the code is not well formed or its numbers make no sense.
    """
    match = CUSTOM_CODE.fullmatch(code) if isinstance(code, str) else None
    if not match:
        raise ValueError(f"Unknown session {code!r}.")
    try:
        day = date.fromisoformat(match[1])
    except ValueError:
        raise ValueError(f"Unknown session {code!r}. {match[1]} is not a real date.") from None
    weeks, break_after, break_weeks = int(match[2]), int(match[3]), int(match[4])
    if not 1 <= weeks <= MAX_CUSTOM_WEEKS:
        raise ValueError(f"Unknown session {code!r}. A session has 1 to {MAX_CUSTOM_WEEKS} teaching weeks.")
    if (break_after == 0) != (break_weeks == 0):
        raise ValueError(f"Unknown session {code!r}. Give both the week the break follows and how long it is, or neither.")
    if break_after >= weeks or break_weeks > MAX_BREAK_WEEKS:
        raise ValueError(
            f"Unknown session {code!r}. The break must come before the last teaching week "
            f"and be at most {MAX_BREAK_WEEKS} weeks long."
        )
    week_1 = day - timedelta(days=day.weekday())  # the Monday of that week
    mondays = _mondays(week_1, weeks + break_weeks)
    if break_weeks:
        breaks = mondays[break_after : break_after + break_weeks]
        teaching = mondays[:break_after] + mondays[break_after + break_weeks :]
    else:
        breaks, teaching = [], mondays
    return {"university": "other", "name": "your session", "weeks": teaching, "breaks": breaks, "exams": None}


def is_custom(session) -> bool:
    """True for a session the student described themselves ("CUSTOM:...")."""
    return isinstance(session, str) and session.startswith(CUSTOM_PREFIX)


def session_info(session: str) -> dict:
    """The calendar for a session code, like "SPR2027", "UNSW_T1_2027" or "CUSTOM:2027-03-01:12:6:1".

    Returns one of the dicts in SESSIONS (its fields are listed above it),
    or the calendar a "CUSTOM:..." code describes.
    Raises ValueError for any other session code.
    """
    if is_custom(session):
        return custom_session(session)
    if session not in SESSIONS:
        raise ValueError(f"Unknown session {session!r}. Use one of: {', '.join(SESSIONS)}.")
    return SESSIONS[session]


def university_name(session: str) -> str:
    """The short name of the session's university, like "UTS" ("your university" for a session the student described)."""
    key = session_info(session)["university"]
    return UNIVERSITIES[key]["name"] if key in UNIVERSITIES else "your university"


def last_week(session: str) -> int:
    """The number of the session's last teaching week: 12 at UTS, 10 at UNSW, 13 at USyd, Macquarie, NUS and NTU, 14 at SMU."""
    return len(session_info(session)["weeks"])


def quiet_week(session: str, week: int) -> str | None:
    """What a numbered week with few classes is called, or None for an ordinary week.

    UNSW's week 6 of every term is "flexibility week", and SMU's week 8 is "recess week".
    """
    return session_info(session).get("quiet_weeks", {}).get(week)


def where_is(session: str, day: date) -> str:
    """Where a day falls in a session, in words.

    One of "week 5", "week 6, UNSW's flexibility week", "a break with no week
    number", "the exam period", "before week 1" or "after the session".
    """
    info = session_info(session)
    for number, monday in enumerate(info["weeks"], 1):
        if monday <= day <= monday + timedelta(days=6):
            called = quiet_week(session, number)
            return f"week {number}, {university_name(session)}'s {called}" if called else f"week {number}"
    if any(monday <= day <= monday + timedelta(days=6) for monday in info["breaks"]):
        return "a break with no week number"
    if info["exams"] and info["exams"][0] <= day <= info["exams"][1]:
        return "the exam period"
    if day < info["weeks"][0]:
        return "before week 1"
    return "after the session"


def open_sessions(today: date) -> dict:
    """The sessions that have not finished yet, so the drop box only offers ones that are still useful.

    A session is finished once its last exam day has passed. They come back
    in the same order as SESSIONS, as {session code: its dict}.
    """
    return {code: info for code, info in SESSIONS.items() if info["exams"][1] >= today}


def finished_universities(today: date) -> list[str]:
    """The short names of the universities whose calendars here have all finished.

    For these, Groot has no session left to offer until next year's dates
    are added to SESSIONS.
    """
    still_open = {info["university"] for info in open_sessions(today).values()}
    return [info["name"] for key, info in UNIVERSITIES.items() if key not in still_open]


def week_start(session: str, week: int) -> date:
    """The Monday that a teaching week starts on.

    Raises ValueError for an unknown session or a week the session does not have.
    """
    weeks = session_info(session)["weeks"]
    # True and False count as numbers in Python, so they are refused on purpose
    if not isinstance(week, int) or isinstance(week, bool) or not 1 <= week <= len(weeks):
        raise ValueError(f"Week {week!r} is not a teaching week. Teaching weeks run from 1 to {len(weeks)}.")
    return weeks[week - 1]


def _clock(time: str) -> tuple[int, int]:
    """'17:30' -> (17, 30). Raises ValueError unless it is a real 24-hour 'HH:MM' time."""
    match = re.fullmatch(r"([01][0-9]|2[0-3]):([0-5][0-9])", time)
    if not match:
        raise ValueError(f"The time must be 24-hour 'HH:MM', like '17:30', but I got {time!r}.")
    return int(match[1]), int(match[2])


def week_date(session: str, week: int, weekday: str, time: str) -> datetime:
    """The date and time for a weekday in a teaching week.

    For example ("SPR2026", 7, "friday", "23:59") is Friday 11 Sep 2026 at 23:59.
    weekday is "monday" to "sunday" and time is 24-hour "HH:MM".
    Raises ValueError if any of them is not valid.
    """
    if weekday not in WEEKDAY_NAMES:
        raise ValueError(f"The weekday must be one of {', '.join(WEEKDAY_NAMES)}, but I got {weekday!r}.")
    hour, minute = _clock(time)
    day = week_start(session, week) + timedelta(days=WEEKDAY_NAMES.index(weekday))
    return datetime(day.year, day.month, day.day, hour, minute)


def teaching_weeks(session: str, first: int, last: int) -> list[tuple[int, date]]:
    """Every teaching week from first to last, as (week number, Monday) pairs.

    A break has no week number, so it is never in the list. For example in
    UTS Spring 2026, weeks 8 to 9 are (8, 14 Sep) and (9, 28 Sep), and the
    StuVac week of 21 Sep is skipped.
    Raises ValueError for an unknown session, a week the session does not
    have, or a first week that comes after the last week.
    """
    if first > last:
        raise ValueError(f"The first week ({first}) comes after the last week ({last}).")
    return [(week, week_start(session, week)) for week in range(first, last + 1)]


def is_public_holiday(day: date) -> bool:
    """True if the day is one of the NSW public holidays in PUBLIC_HOLIDAYS."""
    return day in PUBLIC_HOLIDAYS


def holiday_on(session: str, day: date) -> tuple[str, str] | None:
    """The public holiday on a day where the session's university is, as (place, holiday), or None.

    For example ("NSW", "Good Friday") for a UTS session, or ("Singapore",
    "Vesak Day") for an NUS one. A session the student typed themselves has no
    known country, so it never has holidays.
    """
    key = session_info(session)["university"]
    if key not in UNIVERSITIES:
        return None
    place, holidays = HOLIDAYS[UNIVERSITIES[key]["country"]]
    return (place, holidays[day]) if day in holidays else None
