"""``recall_memory``: what past conversations recorded about the user."""

from typing import Any

from langchain.tools import ToolRuntime, tool

from src.core.langgraph.tools.context import context_user_id
from src.schemas import CoachContext
from src.services.memory import load_user_memory

NOTHING_RECORDED = (
    "nothing beyond the profile is on record for this user; plan from the profile alone"
    " rather than assuming a preference they never stated"
)


@tool
async def recall_memory(runtime: ToolRuntime[CoachContext, Any]) -> dict:
    """Return the user's stated preferences and the habits their past plans revealed.

    Call this once, before choosing the split, so the plan follows what the user
    has already asked for and what they have shown they stick to.
    """

    # The user is read from the runtime rather than taken as an argument, so the model
    # cannot ask for a different user's memory.
    user_id = context_user_id(runtime)
    if not user_id:
        return {"error": NOTHING_RECORDED}

    memory = await load_user_memory(user_id)
    if memory.is_empty:
        return {"error": NOTHING_RECORDED}

    return {"preferences": memory.preferences, "knowledge": memory.knowledge}
