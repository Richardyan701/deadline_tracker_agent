"""Spot sensitive personal details before they leave this computer. Plain code, no AI.

Groot only needs titles, dates, subjects and marks. It never needs a card
number, a tax file number or a password. This module finds details like
those in a piece of text, so the rest of Groot can:

- keep a chat message away from Gemini (agent.py),
- take them out of an outline before it is sent (outline.py), and
- refuse to save them in a deadline (tools.py).

The check runs here, in plain Python, because asking an AI model "is this
sensitive?" would mean sending it the very thing that should not be sent.

What it finds, and how it knows:

    card number        13 to 19 digits that start like a real card (Visa, Mastercard, American
                       Express and so on) and pass the Luhn check every card number passes
    tax file number    8 to 9 digits after the words "TFN" or "tax file number". Nine digits
                       with no such words that pass the Tax Office's own check are called
                       "a number that looks like a tax file number or an ID", because a
                       nine-digit student ID can pass that check by chance
    Medicare number    10 or 11 digits that pass Medicare's own check, either written the
                       way the card shows them (4, 5 and 1 digits) or after the word "Medicare"
    password           what comes after "password is", "password:", "PIN is" and so on,
                       when it has a digit or a symbol in it
    API key            the secret keys of Google ("AIza..."), OpenAI and Anthropic ("sk-...")
                       and GitHub ("ghp_...")
    bank details       a BSB (and the account number after it) after the word "BSB"
    student ID         7 to 9 digits after "student ID", "student number", "SID" or "zID"

WHAT IT CANNOT DO. It only knows patterns. It does not understand meaning,
so it cannot spot health, money or family details written in ordinary words,
a password made only of letters, or anything inside a photo or a scanned
page. The privacy warnings on Groot's pages still matter.

Sometimes it will be wrong the other way and flag an ordinary number. The
checks above make that rare, and the worst that happens is that the student
is asked to send their message again without the number.
"""

import re
from dataclasses import dataclass

# What takes the place of a sensitive detail in text that is sent on
REMOVED = "[removed]"


@dataclass(frozen=True)
class Found:
    """One sensitive detail in a text: what kind it is, and where it starts and ends."""

    kind: str  # for example "card number"
    start: int
    end: int


def _digits(text: str) -> list[int]:
    """The digits in a text, as numbers. '4111 1111' -> [4, 1, 1, 1, 1, 1, 1, 1]."""
    return [int(char) for char in text if char.isdigit()]


# ---------- card numbers ----------

# 13 to 19 digits, with at most one space or hyphen between digits, and no digit on either side
CARD_SHAPE = re.compile(r"(?<![0-9])[0-9](?:[ -]?[0-9]){12,18}(?![0-9])")


def _starts_like_a_card(number: str) -> bool:
    """True if the number has the first digits and the length of a real card network.

    This is what stops other long numbers, like a 13-digit ISBN (which
    starts with 978 or 979), from being taken for a card.
    """
    length = len(number)
    two, three, four = int(number[:2]), int(number[:3]), int(number[:4])
    return (
        (number[0] == "4" and length in (13, 16, 19))  # Visa
        or ((51 <= two <= 55 or 2221 <= four <= 2720) and length == 16)  # Mastercard
        or (two in (34, 37) and length == 15)  # American Express
        or ((two in (36, 38) or 300 <= three <= 305) and length == 14)  # Diners Club
        or ((four == 6011 or two == 65) and length == 16)  # Discover
        or (3528 <= four <= 3589 and length == 16)  # JCB
        or (two == 62 and 16 <= length <= 19)  # UnionPay
    )


def _passes_luhn(digits: list[int]) -> bool:
    """The Luhn check that every card number passes.

    From the right, every second digit is doubled (and 9 is taken off if
    that makes it more than 9). The total must end in 0. A mistyped or
    made-up number fails this 9 times out of 10.
    """
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _is_card(text: str) -> bool:
    digits = _digits(text)
    return _starts_like_a_card("".join(map(str, digits))) and _passes_luhn(digits)


# ---------- tax file numbers ----------

# 9 digits together, or in threes like "123 456 782". A mobile number written
# as "+61 412 345 678" has the same shape, so digits after "+61" are left alone.
TFN_SHAPE = re.compile(r"(?<![0-9])(?<!\+61)(?<!\+61 )[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{3}(?![0-9])")
# 8 or 9 digits soon after the words, whatever the check says
TFN_AFTER_WORDS = re.compile(r"\b(?:tfn|tax file (?:number|no\.?))\b[^0-9\n]{0,20}([0-9](?:[ -]?[0-9]){7,8})(?![0-9])", re.IGNORECASE)
TFN_WEIGHTS = (1, 4, 3, 7, 5, 8, 6, 9, 10)
# What nine digits that pass the check are called when no words say they are a tax file number
TFN_OR_ID = "number that looks like a tax file number or an ID"


def _is_tfn(text: str) -> bool:
    """The Tax Office's check: each digit times its weight, added up, divides by 11 exactly.

    About 1 in 11 nine-digit numbers passes by chance, so this can flag an
    ordinary nine-digit number now and then.
    """
    digits = _digits(text)
    return len(digits) == 9 and sum(digit * weight for digit, weight in zip(digits, TFN_WEIGHTS)) % 11 == 0


# ---------- Medicare numbers ----------

# The way the card shows it: 4 digits, 5 digits, 1 digit, and maybe the person's number on the card
MEDICARE_ON_CARD = re.compile(r"(?<![0-9])[2-6][0-9]{3}[ -][0-9]{5}[ -][0-9](?:[ /-]?[0-9])?(?![0-9])")
# 10 or 11 digits soon after the word
MEDICARE_AFTER_WORD = re.compile(r"\bmedicare\b[^0-9\n]{0,25}([2-6](?:[ /-]?[0-9]){9,10})(?![0-9])", re.IGNORECASE)
MEDICARE_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9)


def _is_medicare(text: str) -> bool:
    """Medicare's check: the first 8 digits times their weights, added up, must end in the 9th digit."""
    digits = _digits(text)
    if len(digits) not in (10, 11) or not 2 <= digits[0] <= 6:
        return False
    return sum(digit * weight for digit, weight in zip(digits, MEDICARE_WEIGHTS)) % 10 == digits[8]


# ---------- passwords, keys, bank details and student IDs ----------

# The value after "password is", "password:", "passcode =" and so on
PASSWORD = re.compile(r"\b(?:pass ?word|passcode|passwd|pwd)\b\s*(?:is|was|:|=)\s*(\S{4,})", re.IGNORECASE)
PIN = re.compile(r"\bpin\b\s*(?:(?:number|code)\s*)?(?:is|was|:|=)\s*([0-9]{4,8})(?![0-9])", re.IGNORECASE)

API_KEYS = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"AIza[0-9A-Za-z_-]{35}"  # Google, which is the kind of key Groot itself uses
    r"|sk-[A-Za-z0-9_-]{20,}"  # OpenAI and Anthropic
    r"|gh[pousr]_[A-Za-z0-9]{36,}"  # GitHub
    r")(?![A-Za-z0-9_-])"
)

# A BSB is 6 digits, and the account number often comes straight after it
BANK = re.compile(r"\bbsb\b[^0-9\n]{0,12}[0-9]{3}[ -]?[0-9]{3}(?![0-9])(?:[^0-9\n]{0,25}[0-9]{6,10}(?![0-9]))?", re.IGNORECASE)

STUDENT_ID = re.compile(
    r"\b(?:student (?:id|number|no\.?)|sid|zid)\b[^0-9a-z\n]{0,6}(?:(?:is|was)\s+)?(z?[0-9]{7,9})(?![0-9])", re.IGNORECASE
)


def _looks_like_a_secret(value: str) -> bool:
    """True if a word after "password is" has a digit or a symbol in it.

    "My password is hunter2!" is flagged. "The password is required by
    Friday" is not, because "required" is an ordinary word. The cost is that
    a password made only of letters is missed.
    """
    return any(not char.isalpha() for char in value.rstrip(".,;:!?")) and bool(value.rstrip(".,;:!?"))


# ---------- finding everything ----------


def find(text: str) -> list[Found]:
    """Every sensitive detail in the text, in the order they appear, with no two overlapping."""
    if not isinstance(text, str) or not text:
        return []
    found = []

    for match in CARD_SHAPE.finditer(text):
        if _is_card(match[0]):
            found.append(Found("card number", match.start(), match.end()))
    for match in TFN_AFTER_WORDS.finditer(text):
        found.append(Found("tax file number", match.start(1), match.end(1)))
    for match in TFN_SHAPE.finditer(text):
        if _is_tfn(match[0]):
            # No words say what it is, and a nine-digit student ID passes the check 1 time in 11
            found.append(Found(TFN_OR_ID, match.start(), match.end()))
    for match in MEDICARE_ON_CARD.finditer(text):
        if _is_medicare(match[0]):
            found.append(Found("Medicare number", match.start(), match.end()))
    for match in MEDICARE_AFTER_WORD.finditer(text):
        if _is_medicare(match[1]):
            found.append(Found("Medicare number", match.start(1), match.end(1)))
    for match in PASSWORD.finditer(text):
        if _looks_like_a_secret(match[1]):
            found.append(Found("password", match.start(1), match.end(1)))
    for match in PIN.finditer(text):
        found.append(Found("password", match.start(1), match.end(1)))
    for match in API_KEYS.finditer(text):
        found.append(Found("API key", match.start(), match.end()))
    for match in BANK.finditer(text):
        found.append(Found("bank account details", match.start(), match.end()))
    for match in STUDENT_ID.finditer(text):
        found.append(Found("student ID", match.start(1), match.end(1)))

    # Earliest first, and the longer one first when two start together. Then
    # drop any that overlaps one already kept, so each piece of text is removed once.
    found.sort(key=lambda one: (one.start, -(one.end - one.start)))
    kept = []
    for one in found:
        if not kept or one.start >= kept[-1].end:
            kept.append(one)
    return kept


def kinds(text: str) -> list[str]:
    """The kinds of sensitive detail in the text, each named once, in the order they first appear."""
    return list(dict.fromkeys(one.kind for one in find(text)))


def redact(text: str) -> tuple[str, list[str]]:
    """The text with every sensitive detail replaced by "[removed]", and the kinds that were found.

    For example "pay with 4111 1111 1111 1111 please" gives
    ("pay with [removed] please", ["card number"]). Text with nothing
    sensitive comes back unchanged with an empty list.
    """
    found = find(text)
    if not found:
        return text, []
    pieces, position = [], 0
    for one in found:
        pieces += [text[position : one.start], REMOVED]
        position = one.end
    pieces.append(text[position:])
    return "".join(pieces), list(dict.fromkeys(one.kind for one in found))


def describe(found_kinds: list[str]) -> str:
    """The kinds in words, for a message: "a card number", or "a card number and a password"."""
    names = [kind if kind.endswith("details") else ("an " if kind[0] in "AEIOU" else "a ") + kind for kind in found_kinds]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
