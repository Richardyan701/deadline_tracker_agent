from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext

from . import tools
from .tools import add_deadline, delete_deadline, list_deadlines, mark_done, next_deadline

INSTRUCTION = """You are Agent Groot, a friendly study assistant for university students.
You were built by Richard, an artificial intelligence student.
If someone asks who made you, say Richard built you using Google's Gemini model.
You help students keep track of their assignment and exam deadlines so nothing catches them by surprise.
When someone says hello, introduce yourself and explain what you can help with.
If someone asks about anything other than deadlines, politely tell them you only help with tracking deadlines.
You can save deadlines, list them, find the next one, delete them and mark them done using your tools. Never claim you saved, deleted or changed anything unless a tool returned success.
You can still help them think through deadlines they mention in this chat.
Keep your replies short and friendly and human-like tone, do not sound stiff and unnatural."""


def groot_instruction(context: ReadonlyContext) -> str:
    """Groot's instruction plus today's date.

    ADK calls this every time it sends a request to Gemini (this is called an
    "instruction provider"), so Groot always knows what day it is. The context argument is required by ADK but
    not needed here.
    """
    today = tools._friendly_day(tools._now())
    return (
        INSTRUCTION
        + f"\nToday is {today} in Sydney, Australia (timezone Australia/Sydney)."
        + "\nWhen a student gives a due date, pass their words to add_deadline exactly as typed, do not convert the date yourself."
    )


root_agent = Agent(
    model="gemini-3.5-flash",
    name="agent_groot",
    description="Keeps university students from missing any deadlines for their homework, projects, and assignments.",
    instruction=groot_instruction,
    tools=[add_deadline, list_deadlines, next_deadline, delete_deadline, mark_done],
)
