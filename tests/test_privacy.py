"""Tests for the sensitive-detail check (privacy.py) and the three places that use it.

Every number below is a well-known test number, not a real person's:
4111 1111 1111 1111 is the standard Visa test card, 123 456 782 is the Tax
Office's example tax file number, and 2123 45670 1 is a Medicare test number.

No test needs an API key or the internet. The chat tests run a whole turn
through ADK with the real Gemini code, and a fake network that records what
would have been sent to Google.
"""

import asyncio
import json
import logging
from datetime import datetime

import httpx
import pytest
from google import genai
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types
from test_outline import FakeClient, answer, raw_item
from test_timetable import make_pdf

from deadline_agent import chat_privacy, documents, outline, privacy, tools
from deadline_agent.agent import root_agent

CARD = "4111 1111 1111 1111"
TFN = "123 456 782"
MEDICARE = "2123 45670 1"
GOOGLE_KEY = "AIza" + "Sy" + "A1b2C3d4E5f6G7h8I9j0" + "KlMnOpQrStUvW"  # made up, the right shape: AIza and 35 more
NOW = datetime(2026, 11, 16, 9, 0)


@pytest.fixture(autouse=True)
def deadlines_file(tmp_path, monkeypatch):
    """Save to a fresh temporary file and freeze the clock."""
    path = tmp_path / "deadlines.json"
    monkeypatch.setenv("DEADLINES_FILE", str(path))
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return path


# ---------- what is found ----------


@pytest.mark.parametrize(
    "text, kind, cleaned",
    [
        # Card numbers: the right first digits and length, and the Luhn check
        (f"pay with {CARD} please", "card number", "pay with [removed] please"),
        ("4111111111111111", "card number", "[removed]"),
        ("card 5555-5555-5555-4444 exp 12/29", "card number", "card [removed] exp 12/29"),  # Mastercard
        ("amex 3782 822463 10005", "card number", "amex [removed]"),  # American Express, 15 digits
        ("6011111111111117", "card number", "[removed]"),  # Discover
        # Tax file numbers: the Tax Office's check, or the words in front
        (f"my tfn is {TFN}", "tax file number", "my tfn is [removed]"),
        ("123456782", "tax file number", "[removed]"),
        ("Tax file number: 12345678", "tax file number", "Tax file number: [removed]"),  # 8 digits after the words
        ("TFN 111-111-111", "tax file number", "TFN [removed]"),  # fails the check, but the words say what it is
        # Medicare numbers: Medicare's check, written like the card or after the word
        (f"card says {MEDICARE}", "Medicare number", "card says [removed]"),
        ("my medicare number is 2123456701", "Medicare number", "my medicare number is [removed]"),
        ("Medicare 2123 45670 1/2", "Medicare number", "Medicare [removed]"),
        # Passwords and PINs
        ("my password is hunter2!", "password", "my password is [removed]"),
        ("Password: Tr0ub4dor&3", "password", "Password: [removed]"),
        ("pwd=abc123", "password", "pwd=[removed]"),
        ("the pass word was s3cret", "password", "the pass word was [removed]"),
        ("my PIN is 4821", "password", "my PIN is [removed]"),
        ("pin code: 123456", "password", "pin code: [removed]"),
        # API keys
        (f"here is my key {GOOGLE_KEY} thanks", "API key", "here is my key [removed] thanks"),
        ("sk-abcdefghijklmnopqrstuvwxyz123456", "API key", "[removed]"),
        ("token ghp_" + "a1B2" * 9, "API key", "token [removed]"),
        # Bank details
        ("BSB 062-000 account 12345678", "bank account details", "[removed]"),
        ("my bsb: 062000", "bank account details", "my [removed]"),
        # Student IDs, only after the words
        ("student id 14567890", "student ID", "student id [removed]"),
        ("Student number: 510123456", "student ID", "Student number: [removed]"),
        ("my zID is z5123456", "student ID", "my zID is [removed]"),
        ("SID 500123456", "student ID", "SID [removed]"),
    ],
)
def test_sensitive_details_are_found_and_taken_out(text, kind, cleaned):
    assert privacy.kinds(text) == [kind]
    assert privacy.redact(text) == (cleaned, [kind])


@pytest.mark.parametrize(
    "text",
    [
        # What students really type to Groot
        "add Essay due next friday 5pm for Writing",
        "33130 Skills Test 1 due 2026-11-20 23:59",
        "COMP1511 quiz on 20/11/2026 at 5pm worth 25%",
        "Assignment 2 worth 25% is due in week 10",
        "what's due this week?",
        "I got 78.5 on the quiz, what do I need for a distinction in 41039?",
        # Numbers that are not sensitive
        "ISBN 9783161484100",  # 13 digits, but no card starts with 978
        "ISBN 978-3-16-148410-0",
        "call the office on 02 9514 2000",
        "my tutor's mobile is 0412 345 678",
        "text +61 412 345 678",  # the same shape as a tax file number, but it follows +61
        "4111 1111 1111 1112",  # a card's shape, but it fails the Luhn check
        "1234 5678 9012 3456",  # starts like no card network
        "123456789",  # nine digits that fail the tax file number check
        "2123456701",  # passes Medicare's check, but ten bare digits could be anything
        "order number 12345678901234567890",  # too long to be a card
        "room CB11.04.400, building 11",
        "student number of enrolments: 1200",  # too short to be an ID
        # Words that only sound sensitive
        "the password is required by friday",  # an ordinary word, with no digit or symbol
        "Password: see Canvas",
        "reset my password before the quiz",
        "pin the notice to the board",
        "BSB is short for bank state branch",
        "check the student ID office hours",
        "",
    ],
)
def test_ordinary_text_is_left_alone(text):
    assert privacy.find(text) == []
    assert privacy.redact(text) == (text, [])


def test_several_details_are_all_taken_out_and_named_once_each():
    text = f"card {CARD} and card 5555 5555 5555 4444, tfn {TFN}, password is abc123"
    cleaned, kinds = privacy.redact(text)
    assert cleaned == "card [removed] and card [removed], tfn [removed], password is [removed]"
    assert kinds == ["card number", "tax file number", "password"]


def test_details_on_different_lines_are_found():
    text = f"Quiz in week 3\nBSB 062-000\nAccount 12345678\nCard\n{CARD}\n"
    assert privacy.kinds(text) == ["bank account details", "card number"]


def test_found_details_never_overlap():
    found = privacy.find(f"my tax file number is {TFN} and student id 14567890")
    assert [one.kind for one in found] == ["tax file number", "student ID"]
    assert all(earlier.end <= later.start for earlier, later in zip(found, found[1:]))


@pytest.mark.parametrize("value", [None, 12345, 4111111111111111, ["x"], b"4111111111111111"])
def test_anything_that_is_not_text_has_nothing_to_find(value):
    assert privacy.find(value) == []


@pytest.mark.parametrize(
    "kinds, words",
    [
        ([], ""),
        (["card number"], "a card number"),
        (["API key"], "an API key"),
        (["bank account details"], "bank account details"),
        (["Medicare number", "password"], "a Medicare number and a password"),
        (["card number", "student ID", "tax file number"], "a card number, a student ID and a tax file number"),
    ],
)
def test_describe(kinds, words):
    assert privacy.describe(kinds) == words


def test_the_luhn_check():
    assert privacy._passes_luhn([int(digit) for digit in "4111111111111111"])
    assert not privacy._passes_luhn([int(digit) for digit in "4111111111111112"])


def test_the_tax_file_number_check():
    assert privacy._is_tfn("123456782")
    assert not privacy._is_tfn("123456783")
    assert not privacy._is_tfn("12345678")


def test_the_medicare_check():
    assert privacy._is_medicare("2123456701")
    assert not privacy._is_medicare("2123456711")  # the check digit is wrong
    assert not privacy._is_medicare("1123456701")  # a Medicare number starts with 2 to 6


# ---------- deadlines: a sensitive title or subject is never saved ----------


@pytest.mark.parametrize(
    "title, subject, message",
    [
        (f"Pay fees with {CARD}", "", "That title looks like it contains a card number, so it was not saved."),
        ("Essay", "password is abc123", "That subject looks like it contains a password, so it was not saved."),
        (f"TFN {TFN} form", "Tax", "That title looks like it contains a tax file number, so it was not saved."),
    ],
)
def test_add_deadline_refuses_sensitive_details(deadlines_file, title, subject, message):
    result = tools.add_deadline(title, "next friday", subject)

    assert result["status"] == "error"
    assert result["message"] == message + " Groot never needs details like that. Take it out and try again."
    assert not deadlines_file.exists()  # nothing was written


def test_edit_deadline_refuses_a_sensitive_new_title_or_subject(deadlines_file):
    assert tools.add_deadline("Essay", "next friday", "Writing")["status"] == "success"

    renamed = tools.edit_deadline("Essay", new_title=f"Essay {CARD}")
    moved = tools.edit_deadline("Essay", new_subject="my pin is 4821")

    assert renamed["status"] == moved["status"] == "error"
    assert "looks like it contains a card number" in renamed["message"]
    assert "looks like it contains a password" in moved["message"]
    saved = json.loads(deadlines_file.read_text(encoding="utf-8"))
    assert [(one["title"], one["subject"]) for one in saved] == [("Essay", "Writing")]
    assert CARD not in deadlines_file.read_text(encoding="utf-8")


def test_ordinary_deadlines_still_save(deadlines_file):
    result = tools.add_deadline("33130 Skills Test 1", "20/11/2026 5pm", "33130 Mathematics 1", 10)
    assert result["status"] == "success"


# ---------- outlines: details are taken out before the outline is sent ----------


def sent_text(client) -> str:
    """Everything the fake Gemini client was given for the one outline, as text."""
    [call] = client.models.calls
    pieces = []
    for part in call["contents"]:
        if isinstance(part, str):
            pieces.append(part)
        elif part.text:
            pieces.append(part.text)
        elif part.inline_data:
            pieces.append(part.inline_data.data.decode("latin-1"))
    return "\n".join(pieces)


def test_a_text_outline_has_sensitive_details_taken_out_before_it_is_sent():
    client = FakeClient(answer(raw_item()))
    removed = []
    notes = f"Quiz 1 is due in week 3.\nPay the lab fee with card {CARD}.\nMy password is hunter2!\n".encode()

    outline.extract_items(notes, filename="notes.txt", client=client, removed=removed)

    sent = sent_text(client)
    assert "Quiz 1 is due in week 3." in sent
    assert "Pay the lab fee with card [removed]." in sent
    assert CARD not in sent and "hunter2" not in sent
    assert removed == ["card number", "password"]


def test_a_pdf_with_a_sensitive_detail_is_sent_as_its_text_without_the_detail():
    client = FakeClient(answer(raw_item()))
    removed = []
    pdf = make_pdf(["33130 Mathematics 1", "Quiz 1 due in week 3", f"Tax file number {TFN}"])

    outline.extract_items(pdf, filename="33130.pdf", client=client, removed=removed)

    [call] = client.models.calls
    assert all(isinstance(part, str) or not part.inline_data for part in call["contents"])  # the file itself did not go
    sent = sent_text(client)
    assert "Quiz 1 due in week 3" in sent
    assert "Tax file number [removed]" in sent
    assert TFN not in sent
    assert removed == ["tax file number"]


def test_an_ordinary_pdf_still_goes_as_the_file_itself():
    client = FakeClient(answer(raw_item()))
    removed = []
    pdf = make_pdf(["33130 Mathematics 1", "Quiz 1 due in week 3", "Contact 02 9514 2000"])

    outline.extract_items(pdf, filename="33130.pdf", client=client, removed=removed)

    [call] = client.models.calls
    assert call["contents"][0].inline_data.data == pdf
    assert removed == []


def test_removed_is_optional():
    client = FakeClient(answer(raw_item()))
    outline.extract_items(f"Quiz in week 3. Card {CARD}".encode(), filename="notes.txt", client=client)
    assert CARD not in sent_text(client)


def test_an_image_cannot_be_checked_and_is_sent_as_it_is():
    document = documents.Document("png", mime_type="image/png", data=b"\x89PNG not really")
    assert outline.without_sensitive_details(document) == (document, [])


def test_pdf_text_of_a_file_that_is_not_a_real_pdf_is_empty():
    assert documents.pdf_text(b"%PDF-1.4\nnot a real pdf") == ""


# ---------- the chat: a whole turn through ADK ----------


def gemini_says(text: str) -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}


def chat(*messages, reply="Sure, I can help with that."):
    """Send Groot each message in one chat. Returns (the text Groot showed for each, every request body sent to Google)."""
    sent = []

    def fake_network(request):
        sent.append(request.content.decode("utf-8"))
        return httpx.Response(200, json=gemini_says(reply))

    async def run():
        client = genai.Client(
            api_key="fake-key-for-tests",
            http_options=types.HttpOptions(async_client_args={"transport": httpx.MockTransport(fake_network)}),
        )
        groot = root_agent.model_copy(update={"model": Gemini(model="gemini-3.5-flash", client=client)})
        runner = InMemoryRunner(agent=groot, app_name="groot_test")
        session = await runner.session_service.create_session(app_name="groot_test", user_id="student")
        shown = []
        for message in messages:
            content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
            texts = []
            async for event in runner.run_async(user_id="student", session_id=session.id, new_message=content):
                if event.content and event.content.parts:
                    texts += [part.text for part in event.content.parts if part.text]
            shown.append(" ".join(texts))
        return shown

    return asyncio.run(run()), sent


def test_groot_checks_every_request_before_it_goes_to_gemini():
    assert root_agent.before_model_callback is chat_privacy.keep_sensitive_details_from_gemini


def test_an_ordinary_message_is_sent_as_usual():
    shown, sent = chat("add Essay due next friday 5pm for Writing")

    assert shown == ["Sure, I can help with that."]
    assert len(sent) == 1
    assert "add Essay due next friday 5pm for Writing" in sent[0]


@pytest.mark.parametrize(
    "message, secret, kinds",
    [
        (f"my card is {CARD}, add Fees due friday", CARD, "a card number"),
        (f"save my tfn {TFN}", TFN, "a tax file number"),
        ("remember my uni password is hunter2!", "hunter2", "a password"),
        (f"is this key ok? {GOOGLE_KEY}", GOOGLE_KEY, "an API key"),
        (f"card {CARD} and my pin is 4821", CARD, "a card number and a password"),
    ],
)
def test_a_message_with_a_sensitive_detail_is_never_sent(message, secret, kinds, caplog):
    with caplog.at_level(logging.WARNING, logger="deadline_agent.chat_privacy"):
        shown, sent = chat(message)

    assert sent == []  # nothing at all went to Google
    assert shown == [
        f"I did not send your last message to Gemini, because it looks like it contains {kinds}. "
        "I never need details like that, and nothing was saved. Please send your message again without it."
    ]
    assert secret not in caplog.text  # the log names the kind, never the detail


def test_the_detail_is_not_sent_with_later_messages_either():
    shown, sent = chat(f"my card is {CARD}", "ok, what's due this week?", "thanks")

    assert shown[0].startswith("I did not send your last message to Gemini")
    assert shown[1:] == ["Sure, I can help with that.", "Sure, I can help with that."]
    assert len(sent) == 2  # only the second and third messages caused a request
    for body in sent:
        assert CARD not in body and "4111" not in body
        assert "my card is [removed]" in body  # the earlier message goes along with the detail taken out
    assert "what's due this week?" in sent[0]


def test_nothing_is_saved_when_a_message_is_not_sent(deadlines_file):
    chat(f"add a deadline called Fees {CARD} due friday")
    assert not deadlines_file.exists()


def test_details_inside_a_tool_result_are_taken_out_too():
    # An old deadlines file could hold a title saved before this check existed
    found = []
    result = {"status": "success", "deadlines": [{"title": f"Pay with {CARD}", "subject": "", "done": False}], "count": 1}
    assert chat_privacy._clean(result, found) == {
        "status": "success", "deadlines": [{"title": "Pay with [removed]", "subject": "", "done": False}], "count": 1,
    }  # fmt: skip
    assert found == ["card number"]
