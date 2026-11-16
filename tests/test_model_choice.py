"""Tests for the GROOT_MODEL setting, which picks the Gemini model Groot uses.

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
        "gpt-5",  # not a Gemini API model, so the Gemini key would not work
        "openai/gpt-5",
        "claude-opus-5",
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
    assert f"so Groot is using {DEFAULT_MODEL}" in caplog.text


def test_no_warning_when_the_setting_is_fine_or_missing(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="deadline_agent.model_choice"):
        chosen_model()
        monkeypatch.setenv("GROOT_MODEL", "gemini-3.5-flash-lite")
        chosen_model()
    assert caplog.text == ""


def test_groot_and_the_outline_reader_use_the_chosen_model():
    # Both read the setting once, when Groot starts
    from deadline_agent import outline
    from deadline_agent.agent import root_agent

    assert root_agent.model == outline.MODEL
    assert model_choice.MODEL_NAME.fullmatch(root_agent.model)
