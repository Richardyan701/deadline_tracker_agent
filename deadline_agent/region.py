"""Which country the student studies in, and so which time zone Groot uses.

Groot keeps every due date as a plain local date and time, like
"2027-03-12 17:00", and compares it with the clock where the student is.
So the time zone decides what "today", "due soon" and "overdue" mean, and
where each deadline lands when it is exported to Google Calendar.

Groot uses Sydney time unless deadline_agent/.env has a line like this:

    GROOT_COUNTRY=SG

The setup script asks for it. A country Groot does not know is ignored
with a warning, so a typo never stops Groot from starting.
"""

import logging
import os
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# The countries Groot knows. "city" is the place named in messages like "around 7:00 PM Sydney time".
# Singapore has one time zone and no daylight saving. Australia has several time zones, and Groot
# uses Sydney's, because the Australian universities it has calendars for are all in Sydney.
# "clock" is how pages name the time every date is shown in. Sydney's offset changes with daylight
# saving (GMT+10 in winter, GMT+11 in summer), so it is named by the city alone.
COUNTRIES = {
    "AU": {"name": "Australia", "time_zone": "Australia/Sydney", "city": "Sydney", "clock": "Sydney time"},
    "SG": {"name": "Singapore", "time_zone": "Asia/Singapore", "city": "Singapore", "clock": "Singapore time (GMT+8)"},
}
DEFAULT_COUNTRY = "AU"

# The setting's name in deadline_agent/.env
SETTING = "GROOT_COUNTRY"

# The same file the keys live in
ENV_FILE = Path(__file__).resolve().parent / ".env"


def chosen_country() -> str:
    """The country code from GROOT_COUNTRY, like "SG", or "AU" if it is not set or not one Groot knows.

    A value already set in the environment wins over the file. Only this one
    setting is read from the file: nothing else in it, like the API key, is
    loaded. Upper or lower case does not matter.
    """
    value = os.environ.get(SETTING)
    if value is None:
        value = dotenv_values(ENV_FILE).get(SETTING) or ""
    value = value.strip()
    if not value:
        return DEFAULT_COUNTRY
    if value.upper() in COUNTRIES:
        return value.upper()
    logger.warning(
        "%s is set to %r, which is not a country Groot knows (%s), so Groot is using %s.",
        SETTING, value, ", ".join(COUNTRIES), COUNTRIES[DEFAULT_COUNTRY]["name"],
    )  # fmt: skip
    return DEFAULT_COUNTRY


def country() -> dict:
    """The chosen country's details: its "name", "time_zone", "city" and "clock"."""
    return COUNTRIES[chosen_country()]
