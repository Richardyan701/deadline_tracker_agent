"""Which Gemini model Groot uses, for the chat and for reading outlines.

Groot uses gemini-3.5-flash unless deadline_agent/.env has a line like this:

    GROOT_MODEL=gemini-3.5-flash-lite

Why choose another one: Google gives every model its own free allowance, so
a lighter model can have a much bigger daily limit on the same key. The
price is that a lighter model can be worse at using Groot's tools or at
reading outlines. Groot's accuracy was measured with gemini-3.5-flash only.

Only models from Google's Gemini API work here (names starting with
"gemini-" or "gemma-"), because they all use the same key.
"""

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# The model Groot was built and measured with
DEFAULT_MODEL = "gemini-3.5-flash"

# The setting's name in deadline_agent/.env
SETTING = "GROOT_MODEL"

# The same file the key lives in
ENV_FILE = Path(__file__).resolve().parent / ".env"

# A Gemini API model name, like "gemini-3.5-flash-lite" or "gemma-4-31b-it"
MODEL_NAME = re.compile(r"(?:gemini|gemma)-[a-z0-9][a-z0-9.-]{0,60}")


def chosen_model() -> str:
    """The model named by GROOT_MODEL, or the default if it is not set or not a Gemini model name.

    Like the key, a GROOT_MODEL already set in the environment wins over
    the file. A name that is not a Gemini model is ignored with a warning,
    so a typo never stops Groot from starting.
    """
    load_dotenv(ENV_FILE)
    value = os.environ.get(SETTING, "").strip()
    if not value:
        return DEFAULT_MODEL
    if not MODEL_NAME.fullmatch(value):
        logger.warning(
            "%s is set to %r, which is not a Gemini model name like 'gemini-3.5-flash-lite', so Groot is using %s.",
            SETTING, value, DEFAULT_MODEL,
        )  # fmt: skip
        return DEFAULT_MODEL
    return value
