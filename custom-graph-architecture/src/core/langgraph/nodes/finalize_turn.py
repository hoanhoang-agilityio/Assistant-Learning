"""The ``finalize_turn`` node: the one place a finished turn persists and settles its reply."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState
from src.services.memory import save_plan

PLAN_SAVED_MESSAGE = (
    "Your plan is saved. Ask me about any part of it, or tell me what to change "
    "whenever your training, schedule or goals shift."
)


class FinalizeTurnUpdate(TypedDict):
    """The state ``finalize_turn`` writes."""

    final_message: str | None
    messages: list[AnyMessage]


async def finalize_turn(state: GraphState) -> FinalizeTurnUpdate:
    """Persist what the turn approved, then settle the message the run ends on."""

    approved = state.get("hitl_decision") == "approve"
    plan = state.get("plan")
    if approved and plan:
        await save_plan(state["user_id"], plan)

    # Every node that ends a run its own way has already written both, so re-writing
    # either here is what would put the same paragraph in the conversation twice.
    final_message = state.get("final_message")
    if final_message:
        return {"final_message": final_message, "messages": []}

    if approved:
        return {
            "final_message": PLAN_SAVED_MESSAGE,
            "messages": [AIMessage(content=PLAN_SAVED_MESSAGE)],
        }

    answer = state.get("qa_answer")
    if answer:
        return {"final_message": answer, "messages": [AIMessage(content=answer)]}

    return {"final_message": None, "messages": []}
