"""Checks Agent Groot's setup: its five tools and its instruction.

Importing the agent needs no API key. The key is only used when the agent
actually talks to Gemini.
"""

import asyncio
from datetime import datetime

from deadline_agent import agent, tools
from deadline_agent.agent import root_agent


def test_root_agent_has_all_five_tools():
    names = {tool.__name__ for tool in root_agent.tools}

    assert names == {
        "add_deadline",
        "list_deadlines",
        "next_deadline",
        "delete_deadline",
        "mark_done",
    }


def test_name_and_model_are_unchanged():
    assert root_agent.name == "agent_groot"
    assert root_agent.model == "gemini-3.5-flash"


def test_instruction_includes_today_in_sydney(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 11, 5, 10, 0))

    # Ask ADK for the instruction the same way it does before calling Gemini
    text, is_provider = asyncio.run(root_agent.canonical_instruction(None))

    assert is_provider is True
    assert text.startswith(agent.INSTRUCTION)  # the original text comes first
    assert "Today is Thursday 5 Nov 2026 in Sydney" in text
    assert "Australia/Sydney" in text
    assert "exactly as typed" in text


def test_instruction_follows_the_clock(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: datetime(2027, 1, 1, 8, 0))

    assert "Today is Friday 1 Jan 2027" in agent.groot_instruction(None)


def test_original_instruction_text_is_kept():
    assert agent.INSTRUCTION.startswith("You are Agent Groot, a friendly study assistant for university students.")
    assert agent.INSTRUCTION.endswith("do not sound stiff and unnatural.")
    assert agent.INSTRUCTION.count("\n") == 8  # all 9 lines are still there
