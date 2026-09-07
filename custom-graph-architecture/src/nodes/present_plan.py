"""The ``present_plan`` node: show the verified plan, and stage it for approval."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState, PendingApproval, TrainingPlan
from src.services.plan_presentation import render_plan_markdown

PLAN_READY_MESSAGE = "I've put your training plan together."

PLAN_REVIEW_ASK = (
    "Take a look and let me know what you think. If you'd like anything changed, "
    "just tell me and I'll adjust it for you."
)


class PresentPlanUpdate(TypedDict):
    """The state ``present_plan`` writes."""

    pending_approval: PendingApproval
    messages: list[AnyMessage]


def build_plan_message(markdown: str | None, intro: str) -> str:
    """Compose the one message a verified plan is shown to the user as."""

    if not markdown:
        return f"{PLAN_READY_MESSAGE}\n\n{PLAN_REVIEW_ASK}"

    return f"{intro}\n\n{markdown}\n\n{PLAN_REVIEW_ASK}"


async def present_plan(state: GraphState) -> PresentPlanUpdate:
    """Stage the verified plan for approval, and show it to the user."""

    plan = state.get("plan")
    markdown = (
        await render_plan_markdown(TrainingPlan.model_validate(plan)) if plan else None
    )
    intro = (plan.get("summary") if plan else None) or PLAN_READY_MESSAGE

    return {
        "pending_approval": PendingApproval(
            source="coach_agent",
            kind="plan",
            summary=markdown or intro,
            payload=plan or {},
        ),
        "messages": [AIMessage(content=build_plan_message(markdown, intro))],
    }
