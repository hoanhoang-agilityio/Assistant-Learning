"""The ``commit_plan`` node: the only place a coach agent's plan is persisted."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState
from src.services.memory import save_plan

PLAN_SAVED_MESSAGE = (
    "Your plan is saved. Ask me about any part of it, or tell me what to change "
    "whenever your training, schedule or goals shift."
)


class CommitPlanUpdate(TypedDict):
    """The state ``commit_plan`` writes."""

    messages: list[AnyMessage]


async def commit_plan(state: GraphState) -> CommitPlanUpdate:
    """Persist the plan ``hitl_agent`` just approved, and confirm it to the user."""

    plan = state.get("plan")
    if plan:
        await save_plan(state["user_id"], plan)

    return {"messages": [AIMessage(content=PLAN_SAVED_MESSAGE)]}
