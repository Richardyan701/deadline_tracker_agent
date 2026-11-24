"""Tests for the GROOT_COUNTRY setting, which picks the time zone Groot uses.

Each test points the setting's file at a temporary .env, so your real
deadline_agent/.env is never read or changed.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from deadline_agent import friendly_errors, region, tools


@pytest.fixture(autouse=True)
def env_file(tmp_path, monkeypatch):
    """A temporary .env, and a temporary deadlines file, so your real ones are never read or changed."""
    path = tmp_path / ".env"
    monkeypatch.setattr(region, "ENV_FILE", path)
    monkeypatch.delenv("GROOT_COUNTRY", raising=False)
    monkeypatch.setenv("DEADLINES_FILE", str(tmp_path / "deadlines.json"))
    return path


def test_the_default_is_australia_on_sydney_time():
    assert region.chosen_country() == "AU"
    assert region.country() == {"name": "Australia", "time_zone": "Australia/Sydney", "city": "Sydney", "clock": "Sydney time"}


@pytest.mark.parametrize("value", ["SG", "sg", " Sg "])
def test_singapore_from_the_file(env_file, value):
    env_file.write_text(f"GOOGLE_API_KEY=not-a-real-key\nGROOT_COUNTRY={value}\n", encoding="utf-8")
    assert region.country() == {
        "name": "Singapore", "time_zone": "Asia/Singapore", "city": "Singapore", "clock": "Singapore time (GMT+8)",
    }


def test_reading_the_country_never_loads_the_key_into_the_environment(env_file, monkeypatch):
    # A test once found the key reappearing after it had been removed, because the whole file was loaded
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    env_file.write_text("GOOGLE_API_KEY=not-a-real-key\nGROOT_COUNTRY=SG\n", encoding="utf-8")
    region.country()
    import os
    assert "GOOGLE_API_KEY" not in os.environ


def test_the_environment_wins_over_the_file(env_file, monkeypatch):
    env_file.write_text("GROOT_COUNTRY=SG\n", encoding="utf-8")
    monkeypatch.setenv("GROOT_COUNTRY", "AU")
    assert region.chosen_country() == "AU"


@pytest.mark.parametrize("value", ["Singapore", "MY", "SGP", "AU;rm", "Australia/Sydney"])
def test_a_country_groot_does_not_know_falls_back_to_australia_with_a_warning(monkeypatch, caplog, value):
    monkeypatch.setenv("GROOT_COUNTRY", value)
    with caplog.at_level(logging.WARNING, logger="deadline_agent.region"):
        assert region.chosen_country() == "AU"
    assert "is not a country Groot knows (AU, SG)" in caplog.text


def test_both_time_zones_exist():
    for details in region.COUNTRIES.values():
        ZoneInfo(details["time_zone"])


# ---------- what Singapore time changes ----------


@pytest.fixture
def singapore(monkeypatch):
    monkeypatch.setattr(tools, "LOCAL_TIME", ZoneInfo("Asia/Singapore"))
    monkeypatch.setattr(tools, "PLACE", region.COUNTRIES["SG"])


def test_singapore_is_8_hours_ahead_of_utc_all_year(singapore):
    # Singapore has no daylight saving, unlike Sydney
    for local in ["2027-01-15 23:59", "2027-07-15 23:59"]:
        moment = tools._utc(tools._parse_due_date(local))
        assert moment.strftime("%Y-%m-%d %H:%M") == local[:11] + "15:59"


def test_the_calendar_export_puts_a_singapore_deadline_at_the_right_moment(singapore):
    lines = tools._event_lines({"title": "Quiz", "due_date": "2027-03-12 17:00", "subject": "", "done": False}, "20270101T000000Z")
    assert "DTSTART:20270312T090000Z" in lines  # 5 PM in Singapore is 9 AM UTC


def test_in_3_hours_stays_right_in_singapore(singapore, monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 12, 22, 30))
    assert tools.add_deadline("Report", "in 3 hours")["deadline"]["due_date"] == "2027-03-13 01:30"


def test_the_limit_reply_names_singapore_time(singapore, monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 12, 13, 0))
    message = friendly_errors._limit_message([
        {"@type": friendly_errors.QUOTA_FAILURE, "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": friendly_errors.RETRY_INFO, "retryDelay": "3600s"},
    ])
    assert "(around 2:00 PM Singapore time)" in message


def test_groots_instruction_says_where_and_when_today_is(singapore, monkeypatch):
    from deadline_agent import agent
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 3, 12, 9, 0))
    assert "Today is Friday 12 Mar 2027 in Singapore, Singapore (timezone Asia/Singapore)." in agent.groot_instruction(None)


def test_singapore_is_always_gmt_plus_8_as_its_label_says():
    from datetime import timedelta
    zone = ZoneInfo("Asia/Singapore")
    for month in range(1, 13):
        assert datetime(2027, month, 15, tzinfo=zone).utcoffset() == timedelta(hours=8)
