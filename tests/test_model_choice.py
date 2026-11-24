"""Tests for the GROOT_MODEL setting, which picks the AI model Groot uses.

Each test points the setting's file at a temporary .env, so your real
deadline_agent/.env is never read or changed.
"""

import logging

import pytest

from deadline_agent import model_choice
from deadline_agent.model_choice import DEFAULT_MODEL, chosen_model


@pytest.fixture(autouse=True)
def env_file(tmp_path, monkeypatch):
    """A temporary .env file, with no GROOT_MODEL set anywhere to start with."""
    path = tmp_path / ".env"
    monkeypatch.setattr(model_choice, "ENV_FILE", path)
    monkeypatch.delenv("GROOT_MODEL", raising=False)
    yield path
    # load_dotenv puts the file's values in the environment, so take ours out again
    monkeypatch.delenv("GROOT_MODEL", raising=False)


def test_the_default_is_the_model_groot_was_measured_with():
    assert DEFAULT_MODEL == "gemini-3.5-flash"
    assert chosen_model() == "gemini-3.5-flash"


@pytest.mark.parametrize(
    "name", ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemma-4-31b-it", "gemini-3.8-flash"]
)
def test_a_gemini_model_named_in_the_file_is_used(env_file, name):
    env_file.write_text(f"GOOGLE_API_KEY=not-a-real-key\nGROOT_MODEL={name}\n", encoding="utf-8")
    assert chosen_model() == name


def test_spaces_around_the_name_are_ignored(monkeypatch):
    monkeypatch.setenv("GROOT_MODEL", "  gemini-3.5-flash-lite  ")
    assert chosen_model() == "gemini-3.5-flash-lite"


def test_the_environment_wins_over_the_file(env_file, monkeypatch):
    env_file.write_text("GROOT_MODEL=gemini-3.1-flash-lite\n", encoding="utf-8")
    monkeypatch.setenv("GROOT_MODEL", "gemini-3.5-flash-lite")
    assert chosen_model() == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_setting_means_the_default(monkeypatch, value):
    monkeypatch.setenv("GROOT_MODEL", value)
    assert chosen_model() == DEFAULT_MODEL


@pytest.mark.parametrize(
    "value",
    [
        "gpt-5",  # another company's model needs "provider/" in front
        "claude-opus-5",
        "mystery/some-model",  # a company Groot does not know
        "openai/",
        "OpenAI/gpt-5",
        "openai/gpt 5",
        "Gemini 3.5 Flash",  # the display name, not the model name
        "GEMINI-3.5-FLASH",
        "gemini-",
        "gemini-3.5-flash; rm -rf /",
        "gemini-3.5-flash\nGOOGLE_API_KEY=x",
        "gemini-" + "a" * 80,
    ],
)
def test_a_name_that_is_not_a_gemini_model_falls_back_to_the_default_with_a_warning(monkeypatch, caplog, value):
    monkeypatch.setenv("GROOT_MODEL", value)
    with caplog.at_level(logging.WARNING, logger="deadline_agent.model_choice"):
        assert chosen_model() == DEFAULT_MODEL
    assert "is not a Gemini model name" in caplog.text
    assert "from a company Groot knows (groq, openai, anthropic, xai, deepseek, openrouter, ollama_chat)" in caplog.text
    assert f"so Groot is using {DEFAULT_MODEL}" in caplog.text


def test_no_warning_when_the_setting_is_fine_or_missing(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="deadline_agent.model_choice"):
        chosen_model()
        monkeypatch.setenv("GROOT_MODEL", "gemini-3.5-flash-lite")
        chosen_model()
    assert caplog.text == ""


# ---------- models from other companies ----------


@pytest.mark.parametrize(
    "name, company, key",
    [
        ("groq/openai/gpt-oss-120b", "Groq", "GROQ_API_KEY"),
        ("openai/gpt-5", "OpenAI", "OPENAI_API_KEY"),
        ("anthropic/claude-opus-5-5", "Anthropic", "ANTHROPIC_API_KEY"),
        ("xai/grok-4", "xAI", "XAI_API_KEY"),
        ("deepseek/deepseek-chat", "DeepSeek", "DEEPSEEK_API_KEY"),
        ("openrouter/meta-llama/llama-4:free", "OpenRouter", "OPENROUTER_API_KEY"),
        ("ollama_chat/qwen3:8b", "Ollama", None),  # runs on this computer, so it needs no key
    ],
)
def test_a_model_from_another_company_is_used(monkeypatch, name, company, key):
    monkeypatch.setenv("GROOT_MODEL", name)

    assert chosen_model() == name
    assert model_choice.provider_of(name) == {"name": company, "key": key}
    assert not model_choice.uses_gemini(name)
    assert model_choice.ai_name() == company


def test_gemini_models_are_googles_and_use_the_google_key():
    for name in ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemma-4-31b-it"):
        assert model_choice.uses_gemini(name)
        assert model_choice.provider_of(name) == {"name": "Gemini", "key": "GOOGLE_API_KEY"}
    assert model_choice.ai_name() == "Gemini"


def test_chat_model_is_the_name_for_gemini_and_a_litellm_object_for_another_company(monkeypatch):
    from google.adk.models.lite_llm import LiteLlm

    assert model_choice.chat_model_alone() == DEFAULT_MODEL  # chat_model() adds the backups, see below
    monkeypatch.setenv("GROOT_MODEL", "groq/openai/gpt-oss-120b")
    model = model_choice.chat_model()
    assert isinstance(model, LiteLlm)
    assert model.model == "groq/openai/gpt-oss-120b"


def test_without_the_litellm_library_groot_falls_back_to_gemini_with_a_warning(monkeypatch, caplog):
    import sys

    monkeypatch.setenv("GROOT_MODEL", "groq/openai/gpt-oss-120b")
    monkeypatch.setitem(sys.modules, "google.adk.models.lite_llm", None)  # makes the import fail
    with caplog.at_level(logging.WARNING, logger="deadline_agent.model_choice"):
        assert model_choice.chat_model() == DEFAULT_MODEL
    assert "the LiteLLM library that other companies' models need is not installed" in caplog.text


# ---------- backup models for when one is busy ----------


def test_a_gemini_model_gets_the_other_gemini_models_as_backups():
    assert model_choice.model_chain() == ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


def test_the_chosen_model_goes_first_and_is_not_repeated(monkeypatch):
    monkeypatch.setenv("GROOT_MODEL", "gemini-3.5-flash-lite")
    # 3.1 Flash-Lite comes before 3.5 Flash, because it failed far less often in the week of hourly checks
    assert model_choice.model_chain() == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"]
    monkeypatch.setenv("GROOT_MODEL", "gemma-4-31b-it")
    assert model_choice.model_chain()[0] == "gemma-4-31b-it" and len(model_choice.model_chain()) == 4


@pytest.mark.parametrize("value", ["off", "OFF", " Off "])
def test_backups_can_be_turned_off(monkeypatch, value):
    monkeypatch.setenv("GROOT_BACKUPS", value)
    assert model_choice.model_chain() == ["gemini-3.5-flash"]
    assert model_choice.chat_model() == "gemini-3.5-flash"


def test_another_companys_model_gets_no_backups(monkeypatch):
    # A backup would send the student's words to Google while the pages name the other company
    monkeypatch.setenv("GROOT_MODEL", "groq/openai/gpt-oss-120b")
    assert model_choice.model_chain() == ["groq/openai/gpt-oss-120b"]


def test_the_chat_model_moves_on_when_one_is_busy_used_up_or_retired():
    from google.adk.models import FallbackModel

    model = model_choice.chat_model()
    assert isinstance(model, FallbackModel)
    assert model.models == model_choice.model_chain()
    assert {404, 429, 500, 502, 503, 504} <= model.retriable_status_codes
