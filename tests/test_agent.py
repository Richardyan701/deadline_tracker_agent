"""Checks that Agent Groot has all five tools registered.

Importing the agent needs no API key. The key is only used when the agent
actually talks to Gemini.
"""

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
