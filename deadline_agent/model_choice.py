"""Which AI model Groot uses, for the chat and for reading outlines.

Groot uses Google's gemini-3.5-flash unless deadline_agent/.env has a line
like one of these:

    GROOT_MODEL=gemini-3.5-flash-lite        another Gemini model, with the same Google key
    GROOT_MODEL=groq/openai/gpt-oss-120b     a model from another company, written "provider/model"

A model from another company also needs that company's own key in the same
file, for example GROQ_API_KEY=... (PROVIDERS below lists each key's name).

Why choose another one: every model has its own free allowance and its own
strengths. The price is that another model can be worse at using Groot's
tools or at reading outlines. Groot's accuracy was measured with
gemini-3.5-flash, and the chat was also measured with gemini-3.5-flash-lite.

Gemini models are run by ADK's own Gemini code. Every other model is run
through LiteLLM, a library that speaks to many companies' models in one way.
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

# The same file the keys live in
ENV_FILE = Path(__file__).resolve().parent / ".env"

# A Gemini API model name, like "gemini-3.5-flash-lite" or "gemma-4-31b-it"
MODEL_NAME = re.compile(r"(?:gemini|gemma)-[a-z0-9][a-z0-9.-]{0,60}")

# The other companies Groot can use. The part of GROOT_MODEL before the first
# "/" picks one. "name" is what Groot calls it on its pages and in the chat,
# and "key" is the line its key goes on in .env (None when it needs no key).
PROVIDERS = {
    "groq": {"name": "Groq", "key": "GROQ_API_KEY"},
    "openai": {"name": "OpenAI", "key": "OPENAI_API_KEY"},
    "anthropic": {"name": "Anthropic", "key": "ANTHROPIC_API_KEY"},
    "xai": {"name": "xAI", "key": "XAI_API_KEY"},
    "deepseek": {"name": "DeepSeek", "key": "DEEPSEEK_API_KEY"},
    "openrouter": {"name": "OpenRouter", "key": "OPENROUTER_API_KEY"},
    # Ollama runs a model on this computer, so nothing is sent to any company and no key is needed
    "ollama_chat": {"name": "Ollama", "key": None},
}

# "provider/model", like "groq/openai/gpt-oss-120b" or "ollama_chat/qwen3:8b"
OTHER_MODEL_NAME = re.compile(r"([a-z_]{2,20})/[A-Za-z0-9][A-Za-z0-9._:/-]{0,100}")

# Google's own name and key, in the same shape as a PROVIDERS entry
GEMINI = {"name": "Gemini", "key": "GOOGLE_API_KEY"}


def _use_default(value: str, why: str) -> str:
    logger.warning("%s is set to %r, %s, so Groot is using %s.", SETTING, value, why, DEFAULT_MODEL)
    return DEFAULT_MODEL


def chosen_model() -> str:
    """The model named by GROOT_MODEL, or the default if it is not set or not a name Groot knows.

    Like the keys, a GROOT_MODEL already set in the environment wins over
    the file. A name Groot does not know is ignored with a warning, so a
    typo never stops Groot from starting.
    """
    load_dotenv(ENV_FILE)
    value = os.environ.get(SETTING, "").strip()
    if not value:
        return DEFAULT_MODEL
    if MODEL_NAME.fullmatch(value):
        return value
    other = OTHER_MODEL_NAME.fullmatch(value)
    if other and other[1] in PROVIDERS:
        return value
    return _use_default(
        value,
        "which is not a Gemini model name like 'gemini-3.5-flash-lite' or a 'provider/model' name "
        f"from a company Groot knows ({', '.join(PROVIDERS)})",
    )


def provider_of(model: str) -> dict:
    """The company behind a model name: its "name" for messages and the name of its "key" in .env."""
    if MODEL_NAME.fullmatch(model):
        return GEMINI
    return PROVIDERS[model.partition("/")[0]]


def uses_gemini(model: str) -> bool:
    """True if the model is one of Google's, run by ADK's own Gemini code."""
    return provider_of(model) is GEMINI


def ai_name() -> str:
    """What Groot calls the AI it is using, like "Gemini" or "Groq"."""
    return provider_of(chosen_model())["name"]


def chat_model():
    """What ADK's Agent needs as its model: the name for a Gemini model, or a LiteLlm object for any other.

    LiteLLM is an extra library. If it is not installed, Groot says so and
    falls back to the default Gemini model instead of failing to start.
    """
    model = chosen_model()
    if uses_gemini(model):
        return model
    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError:
        return _use_default(model, "but the LiteLLM library that other companies' models need is not installed")
    return LiteLlm(model=model)
