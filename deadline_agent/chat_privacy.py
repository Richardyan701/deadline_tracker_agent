"""Keep sensitive details in the chat away from Gemini.

ADK calls keep_sensitive_details_from_gemini just before every request to
Gemini (it is Groot's "before_model_callback"). At that moment the request
is still on this computer, so this is the last place to check it.

Two things happen:

1. If the student's newest message has something like a card number or a
   password in it (see privacy.py), the request is not sent at all. Groot
   answers with a short note instead, asking them to send the message again
   without it.
2. Every other piece of text in the request (earlier messages, tool
   results and Groot's instruction) has such details replaced by
   "[removed]". So a detail typed earlier in the chat is never sent with a
   later message either.

The student's own words still show in the chat window, which is on their
own computer. What changes is only what goes to Google.
"""

import logging

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from . import model_choice, privacy

logger = logging.getLogger(__name__)


def not_sent_message(found_kinds: list[str]) -> str:
    """What Groot says instead of sending the message on."""
    return (
        f"I did not send your last message to {model_choice.ai_name()}, because it looks like it contains "
        f"{privacy.describe(found_kinds)}. "
        "I never need details like that, and nothing was saved. Please send your message again without it."
    )


def _clean(value, found: list[str]):
    """The same value with sensitive details taken out of every piece of text inside it.

    Tool calls and tool results are dicts and lists with text inside, so
    this goes through them piece by piece. The kinds found are added to found.
    """
    if isinstance(value, str):
        cleaned, kinds = privacy.redact(value)
        found += kinds
        return cleaned
    if isinstance(value, dict):
        return {key: _clean(item, found) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item, found) for item in value]
    return value


def _clean_content(content: types.Content) -> list[str]:
    """Take sensitive details out of one message in the request. Returns the kinds found in its text."""
    in_text, elsewhere = [], []
    for part in content.parts or []:
        if part.text:
            part.text = _clean(part.text, in_text)
        if part.function_call and part.function_call.args:
            part.function_call.args = _clean(part.function_call.args, elsewhere)
        if part.function_response and part.function_response.response:
            part.function_response.response = _clean(part.function_response.response, elsewhere)
    return in_text


def keep_sensitive_details_from_gemini(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Groot's before_model_callback: clean the request, and stop it if the newest message is sensitive.

    Returning None tells ADK to send the (cleaned) request. Returning a reply
    tells ADK to show that reply and send nothing. The context argument is
    required by ADK but not needed here.
    """
    contents = llm_request.contents or []
    found_in = [_clean_content(content) for content in contents]

    config = llm_request.config
    if config is not None and isinstance(config.system_instruction, str):
        config.system_instruction = _clean(config.system_instruction, [])

    # The newest thing in the request is the student's message, unless Groot is
    # in the middle of a turn and the newest thing is a tool result (no text).
    if contents and contents[-1].role == "user" and found_in[-1]:
        kinds = list(dict.fromkeys(found_in[-1]))
        # Only the kinds are logged, never the details themselves
        logger.warning("A chat message was not sent to the AI model because it looked like it contained: %s", ", ".join(kinds))
        return LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=not_sent_message(kinds))]))
    return None
