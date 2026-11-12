"""Tests for Groot's friendly replies when a Gemini call fails (deadline_agent/friendly_errors.py).

No API key and no internet needed. The first tests send a whole chat turn
through ADK with the real Gemini model class and the real google-genai code.
Only the network is fake: a stand-in answers each request with an error body
shaped like the ones Google sends, so the error reaches Groot the same way it
does in adk web. The later tests check the wording for each case.
"""

import asyncio
import logging
from datetime import datetime

import httpx
import pytest
from google import genai
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import errors, types

from deadline_agent import tools
from deadline_agent.agent import root_agent
from deadline_agent.friendly_errors import (
    BAD_KEY,
    NO_KEY,
    SOME_LIMIT,
    TIMEOUT,
    friendly_message,
    friendly_model_error,
)

# Pretend "now" is Wednesday 4 Nov 2026, 1:23 PM in Sydney
NOW = datetime(2026, 11, 4, 13, 23)

PER_DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
TOKENS_PER_MINUTE = "GenerateContentInputTokensPerModelPerMinute-FreeTier"

FAKE_KEY = "not-a-real-key"


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    """A fresh temporary deadlines file, a frozen clock, and no key from your real environment."""
    monkeypatch.setenv("DEADLINES_FILE", str(tmp_path / "deadlines.json"))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_USE_ENTERPRISE", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(name, raising=False)


# ---------- error bodies shaped like the ones Google sends ----------


def error_body(code, status, *details):
    return {"error": {"code": code, "message": "shortened", "status": status, "details": list(details)}}


def quota_failure(*quota_ids):
    """Which free-tier limits ran out."""
    return {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
            {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", "quotaId": quota_id}
            for quota_id in quota_ids
        ],
    }


def retry_info(delay):
    """How long Google says to wait, like "20215s"."""
    return {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}


def limit_error(*details):
    return error_body(429, "RESOURCE_EXHAUSTED", *details)


# The reply for a key that is wrong, as reported in public bug reports
BAD_KEY_BODY = error_body(
    400,
    "INVALID_ARGUMENT",
    {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "API_KEY_INVALID",
        "domain": "googleapis.com",
        "metadata": {"service": "generativelanguage.googleapis.com"},
    },
    {"@type": "type.googleapis.com/google.rpc.LocalizedMessage", "locale": "en-US", "message": "API key not valid."},
)

# A successful reply where Gemini asks for one tool call
ADD_ESSAY = {
    "candidates": [{
        "content": {
            "role": "model",
            "parts": [{"functionCall": {"name": "add_deadline", "args": {"title": "Essay", "due_date": "friday"}}}],
        },
        "finishReason": "STOP",
    }]
}

DAILY_MESSAGE = (
    "Gemini's free daily limit is used up. It resets in about 5 hours 37 minutes "
    "(around 7:00 PM Sydney time). Your saved deadlines are safe."
)


# ---------- a whole turn through ADK with the real Gemini code ----------


def chat(*replies, key=FAKE_KEY, stream=False):
    """Send Groot "hi" the way adk web does, and return the text of every reply it shows.

    Each request to Gemini gets the next of replies, given as (status code, JSON body),
    or an exception to raise as if the network itself failed.
    With key=None there is no API key at all, so no request is ever sent.
    """
    replies = list(replies)

    def fake_network(request):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body = reply
        return httpx.Response(status, json=body)

    async def run():
        if key is None:
            model = Gemini(model="gemini-3.5-flash")  # builds its own client and finds no key
        else:
            client = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(async_client_args={"transport": httpx.MockTransport(fake_network)}),
            )
            model = Gemini(model="gemini-3.5-flash", client=client)
        groot = root_agent.model_copy(update={"model": model})
        runner = InMemoryRunner(agent=groot, app_name="groot_test")
        session = await runner.session_service.create_session(app_name="groot_test", user_id="student")
        message = types.Content(role="user", parts=[types.Part.from_text(text="hi")])
        config = RunConfig(streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE)
        texts = []
        async for event in runner.run_async(
            user_id="student", session_id=session.id, new_message=message, run_config=config
        ):
            if event.content and event.content.parts:
                texts += [part.text for part in event.content.parts if part.text]
        return texts

    return asyncio.run(run())


def test_groot_uses_the_friendly_error_callback():
    assert root_agent.on_model_error_callback is friendly_model_error


@pytest.mark.parametrize("stream", [False, True], ids=["plain", "streaming"])
def test_daily_limit_shows_when_it_resets_in_sydney_time(stream):
    # 20215 seconds after 1:23 PM is 6:59:55 PM, which is about 7:00 PM
    texts = chat((429, limit_error(quota_failure(PER_DAY), retry_info("20215s"))), stream=stream)

    assert texts == [DAILY_MESSAGE]


def test_per_minute_limit_says_how_long_to_wait():
    texts = chat((429, limit_error(quota_failure(PER_MINUTE), retry_info("30s"))))

    assert texts == ["That was a lot of messages in a minute. Wait about 30 seconds and try again."]


def test_limit_with_no_details_gives_a_general_reply():
    texts = chat((429, {"error": {"code": 429, "message": "Resource exhausted.", "status": "RESOURCE_EXHAUSTED"}}))

    assert texts == [SOME_LIMIT]


def test_invalid_key_gets_a_one_sentence_fix():
    assert chat((400, BAD_KEY_BODY)) == [BAD_KEY]


def test_missing_key_gets_a_one_sentence_fix():
    assert chat(key=None) == [NO_KEY]


def test_timeout_asks_to_send_again():
    texts = chat((504, error_body(504, "DEADLINE_EXCEEDED")))

    assert texts == [TIMEOUT]


def test_limit_after_a_tool_ran_keeps_the_saved_deadline():
    # A message that uses a tool needs two requests. Here the first works and the second hits the limit.
    texts = chat((200, ADD_ESSAY), (429, limit_error(quota_failure(PER_DAY), retry_info("20215s"))))

    assert texts == [DAILY_MESSAGE]
    assert [d["title"] for d in tools.list_deadlines()["deadlines"]] == ["Essay"]


@pytest.mark.parametrize(
    "status, body",
    [
        (503, error_body(503, "UNAVAILABLE")),  # Gemini is overloaded
        (500, error_body(500, "INTERNAL")),
        (404, error_body(404, "NOT_FOUND")),  # for example a model name that does not exist
        (400, error_body(400, "INVALID_ARGUMENT")),  # a bad request that is not about the key
        (403, error_body(403, "PERMISSION_DENIED")),
    ],
)
def test_other_gemini_errors_are_still_raised(status, body):
    with pytest.raises(errors.APIError) as raised:
        chat((status, body))

    assert raised.value.code == status


def test_errors_that_are_not_from_gemini_are_still_raised():
    with pytest.raises(httpx.ConnectError, match="no internet"):
        chat(httpx.ConnectError("no internet"))


def test_unknown_errors_return_none_so_adk_raises_them():
    assert friendly_model_error(None, None, RuntimeError("something broke")) is None
    assert friendly_model_error(None, None, ValueError("some other value error")) is None


def test_the_real_error_is_still_logged_but_never_the_key(caplog):
    with caplog.at_level(logging.WARNING, logger="deadline_agent.friendly_errors"):
        chat((429, limit_error(quota_failure(PER_DAY), retry_info("20215s"))))

    assert "RESOURCE_EXHAUSTED" in caplog.text
    assert PER_DAY in caplog.text
    assert FAKE_KEY not in caplog.text


# ---------- the wording, case by case ----------


def limit_message(*details):
    """What Groot says for a 429 with these details."""
    return friendly_message(errors.ClientError(429, limit_error(*details)))


@pytest.mark.parametrize(
    "delay, wait",
    [
        ("30s", "about 30 seconds"),
        ("55s", "about 55 seconds"),
        ("1.5s", "about 2 seconds"),  # rounded up, never less than Google asked
        ("0s", "about 1 second"),
        ("60s", "about 1 minute"),
        ("150s", "about 2 minutes"),
    ],
)
def test_per_minute_wait_in_friendly_words(delay, wait):
    message = limit_message(quota_failure(PER_MINUTE), retry_info(delay))

    assert message == f"That was a lot of messages in a minute. Wait {wait} and try again."


def test_a_per_minute_token_limit_counts_as_per_minute():
    message = limit_message(quota_failure(TOKENS_PER_MINUTE), retry_info("12s"))

    assert message == "That was a lot of messages in a minute. Wait about 12 seconds and try again."


def test_per_minute_with_no_delay_waits_about_a_minute():
    message = limit_message(quota_failure(PER_MINUTE))

    assert message == "That was a lot of messages in a minute. Wait about a minute and try again."


def test_daily_wins_when_both_limits_ran_out():
    # A real reply can list several limits at once, and waiting a minute does not help the daily one
    message = limit_message(quota_failure(TOKENS_PER_MINUTE, PER_MINUTE, PER_DAY), retry_info("20215s"))

    assert message == DAILY_MESSAGE


def test_daily_with_no_delay_says_try_again_later():
    message = limit_message(quota_failure(PER_DAY))

    assert message == "Gemini's free daily limit is used up. Please try again later. Your saved deadlines are safe."


@pytest.mark.parametrize(
    "now, delay, wait, when",
    [
        # From 1:23 PM the same day
        (datetime(2026, 11, 4, 13, 23), "20215s", "about 5 hours 37 minutes", "7:00 PM"),
        (datetime(2026, 11, 4, 13, 23), "3600s", "about 1 hour", "2:23 PM"),
        # From 9 PM the reset is the next evening
        (datetime(2026, 11, 4, 21, 0), "79200s", "about 22 hours", "7:00 PM tomorrow"),
        # Clocks go forward at 2 AM on Sunday 4 Oct 2026, so 12 hours after 8 PM is 9 AM, not 8 AM
        (datetime(2026, 10, 3, 20, 0), "43200s", "about 12 hours", "9:00 AM tomorrow"),
        # Just before midnight rounds into the next day
        (datetime(2026, 11, 4, 23, 59), "50s", "about 50 seconds", "12:00 AM tomorrow"),
        # Further away than tomorrow gives the whole date
        (datetime(2026, 11, 4, 13, 23), "259200s", "about 72 hours", "Saturday 7 Nov 2026, 1:23 PM"),
    ],
)
def test_daily_reset_time_in_sydney(monkeypatch, now, delay, wait, when):
    monkeypatch.setattr(tools, "_now", lambda: now)

    message = limit_message(quota_failure(PER_DAY), retry_info(delay))

    assert message == (
        f"Gemini's free daily limit is used up. It resets in {wait} (around {when} Sydney time)."
        " Your saved deadlines are safe."
    )


@pytest.mark.parametrize("delay", ["20215", "abc", 20215, None, "-5s", "9999999999s"])
def test_an_odd_delay_counts_as_no_delay(delay):
    message = limit_message(quota_failure(PER_DAY), retry_info(delay))

    assert message == "Gemini's free daily limit is used up. Please try again later. Your saved deadlines are safe."


def test_an_unknown_limit_gives_the_general_reply():
    assert limit_message(quota_failure("SomethingPerHour"), retry_info("30s")) == SOME_LIMIT


@pytest.mark.parametrize(
    "body",
    [
        "not json at all",
        ["a list", "of two things"],
        {"error": "just text"},
        {"error": {"code": 429, "details": "not a list"}},
        {"error": {"code": 429, "details": ["not a dict", 5]}},
        {"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": 5}]}},
        {"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": ["x", {"quotaId": 7}]}]}},
    ],
)
def test_strange_details_never_crash(body):
    assert friendly_message(errors.ClientError(429, body)) == SOME_LIMIT


def test_bad_key_is_found_by_its_reason_code():
    assert friendly_message(errors.ClientError(400, BAD_KEY_BODY)) == BAD_KEY


def test_the_missing_key_error_from_google_genai_is_recognised():
    # Build the real error, so the test fails if a new google-genai changes its wording
    with pytest.raises(ValueError) as raised:
        genai.Client()

    assert friendly_message(raised.value) == NO_KEY


def test_replies_are_short_and_have_no_dashes_or_semicolons():
    replies = [BAD_KEY, NO_KEY, TIMEOUT, SOME_LIMIT, DAILY_MESSAGE]
    for reply in replies:
        assert ";" not in reply and " - " not in reply
    # The key and timeout replies are one sentence each
    for reply in (BAD_KEY, NO_KEY, TIMEOUT):
        assert reply.count(". ") == 0 and reply.endswith(".")
