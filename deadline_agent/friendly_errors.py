"""Short, friendly replies for when Groot cannot get an answer from Gemini.

When a request to Gemini fails, ADK calls friendly_model_error (agent.py gives
it to Groot as its on_model_error_callback). For the problems a student can fix
or wait out, it returns a short reply, and ADK shows that in the chat instead
of a long red error:

- 429 RESOURCE_EXHAUSTED: a free tier limit is used up, per day or per minute
- no API key, or a key that Google says is not valid
- 504 DEADLINE_EXCEEDED: Gemini took too long to answer

For any other error it returns None, and ADK then raises that error exactly as
before, so nothing else is hidden.

The 429 details come from Google, and look like this (shortened):

    {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20215s"}]}}
"""

import logging
import math
import re
from datetime import timedelta

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import errors, types

from . import tools

logger = logging.getLogger(__name__)

# The "@type" names Google gives the details we read
QUOTA_FAILURE = "type.googleapis.com/google.rpc.QuotaFailure"  # which limit ran out
RETRY_INFO = "type.googleapis.com/google.rpc.RetryInfo"  # how long to wait
ERROR_INFO = "type.googleapis.com/google.rpc.ErrorInfo"  # a reason code, like API_KEY_INVALID

# The start of the error google-genai raises when there is no key at all
MISSING_KEY_TEXT = "No API key was provided"

SAFE = "Your saved deadlines are safe."
NO_KEY = "I can't find your Gemini API key, so please run the setup script again and then restart Groot."
BAD_KEY = (
    "Gemini says your API key is not valid, so please run the setup script again, "
    "paste the whole key and then restart Groot."
)
TIMEOUT = "Gemini took too long to answer, so please send your message again."
DAILY_LIMIT = "Gemini's free daily limit is used up."
MINUTE_LIMIT = "That was a lot of messages in a minute."
# For a 429 that does not say which limit ran out
SOME_LIMIT = (
    "Gemini's free limit has been reached for now. Wait a minute and try again, "
    "and if it still fails, the daily limit is probably used up. " + SAFE
)


def friendly_model_error(
    callback_context: CallbackContext, llm_request: LlmRequest, error: Exception
) -> LlmResponse | None:
    """Groot's on_model_error_callback: a chat reply for an error we know, or None.

    Returning None tells ADK to raise the error as before. The two context
    arguments are required by ADK but not needed here.
    """
    message = friendly_message(error)
    if message is None:
        return None
    # The terminal still shows what really happened, so nothing is hidden from the developer
    logger.warning("Gemini failed, so Groot showed a friendly reply instead. The error was: %s", error)
    return LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=message)]))


def friendly_message(error: Exception) -> str | None:
    """The reply for an error a student can do something about, or None for any other error."""
    if isinstance(error, ValueError) and str(error).startswith(MISSING_KEY_TEXT):
        return NO_KEY
    if not isinstance(error, errors.APIError):
        return None  # any other error that is not an error reply from Gemini is not one of ours
    details = _details(error)
    if error.code == 429:
        return _limit_message(details)
    if _detail(details, ERROR_INFO).get("reason") == "API_KEY_INVALID":
        return BAD_KEY
    if error.code == 504:
        return TIMEOUT
    return None


# ---------- reading the details Google sends ----------


def _details(error: errors.APIError) -> list:
    """The list of details in the error Google sent, or [] if there are none.

    The error comes from outside, so anything that is not the usual shape
    counts as no details instead of crashing.
    """
    body = error.details
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return []
    details = body["error"].get("details")
    if not isinstance(details, list):
        return []
    return [item for item in details if isinstance(item, dict)]


def _detail(details: list, type_name: str) -> dict:
    """The first detail with this "@type", or {} if there is none."""
    for item in details:
        if item.get("@type") == type_name:
            return item
    return {}


def _quota_ids(details: list) -> list:
    """The names of the limits that ran out, like 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'."""
    violations = _detail(details, QUOTA_FAILURE).get("violations")
    if not isinstance(violations, list):
        return []
    return [v["quotaId"] for v in violations if isinstance(v, dict) and isinstance(v.get("quotaId"), str)]


def _retry_seconds(details: list) -> float | None:
    """How many seconds Google says to wait, from a retryDelay like '20215s', or None.

    At most 9 digits (about 31 years), so a silly number cannot go past the year 9999.
    """
    delay = _detail(details, RETRY_INFO).get("retryDelay")
    match = re.fullmatch(r"([0-9]{1,9}(?:\.[0-9]+)?)s", delay) if isinstance(delay, str) else None
    return float(match[1]) if match else None


# ---------- the reply for a used up limit (429) ----------


def _limit_message(details: list) -> str:
    """The reply for a 429, worked out from which limit ran out and how long to wait.

    The daily limit is checked first, because when it is used up, waiting a
    minute does not help even if a per minute limit ran out too.
    """
    quota_ids = _quota_ids(details)
    seconds = _retry_seconds(details)
    if any("PerDay" in quota_id for quota_id in quota_ids):
        if seconds is None:
            return f"{DAILY_LIMIT} Please try again later. {SAFE}"
        return (
            f"{DAILY_LIMIT} It resets in {_how_long(seconds)} "
            f"(around {_sydney_time(seconds)} Sydney time). {SAFE}"
        )
    if any("PerMinute" in quota_id for quota_id in quota_ids):
        wait = "about a minute" if seconds is None else _how_long(seconds)
        return f"{MINUTE_LIMIT} Wait {wait} and try again."
    return SOME_LIMIT


def _how_long(seconds: float) -> str:
    """A wait in friendly words, like 'about 40 seconds' or 'about 5 hours 37 minutes'."""
    if seconds < 60:
        # Rounded up, so we never say to wait less than Google asked
        return "about " + tools._plural(max(1, math.ceil(seconds)), "second")
    hours, minutes = divmod(round(seconds / 60), 60)
    parts = [tools._plural(hours, "hour")] if hours else []
    if minutes:
        parts.append(tools._plural(minutes, "minute"))
    return "about " + " ".join(parts)


def _sydney_time(seconds: float) -> str:
    """The Sydney clock time that many seconds from now, to the nearest minute.

    For example '7:00 PM', '7:00 PM tomorrow', or the whole date if it is further away.
    """
    now = tools._now()
    # Added in UTC, so it is still right on the nights the clocks change for daylight saving
    later = (tools._utc(now) + timedelta(seconds=seconds)).astimezone(tools.SYDNEY)
    later += timedelta(seconds=30)  # with the seconds then ignored, this rounds to the nearest minute
    clock = f"{later.hour % 12 or 12}:{later.minute:02d} {'AM' if later.hour < 12 else 'PM'}"
    if later.date() == now.date():
        return clock
    if later.date() == now.date() + timedelta(days=1):
        return clock + " tomorrow"
    return tools._friendly(later)
