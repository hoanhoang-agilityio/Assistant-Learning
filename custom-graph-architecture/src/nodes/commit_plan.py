"""The ``commit_plan`` node: the only place a coach agent's plan is persisted."""

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import ApprovalCycleReset, GraphState, cleared_approval
from src.services.memory import save_plan

PLAN_SAVED_MESSAGE = (
    "Your plan is saved. Ask me about any part of it, or tell me what to change "
    "whenever your training, schedule or goals shift."
)


class CommitPlanUpdate(ApprovalCycleReset):
    """The state ``commit_plan`` writes."""

    messages: list[AnyMessage]


async def commit_plan(state: GraphState) -> CommitPlanUpdate:
    """Persist the plan ``plan_approval`` just approved, confirm it, and close the review."""

    plan = state.get("plan")
    if plan:
        await save_plan(state["user_id"], plan)

    return {
        **cleared_approval(),
        "messages": [AIMessage(content=PLAN_SAVED_MESSAGE)],
    }
