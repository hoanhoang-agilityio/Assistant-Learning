"""The ``present_plan`` node: write the verified plan into the conversation."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState, TrainingPlan
from src.services.plan_presentation import render_plan_markdown

PLAN_READY_MESSAGE = "I've put your training plan together."

PLAN_REVIEW_ASK = (
    "Take a look and let me know what you think. If you'd like anything changed, "
    "just tell me and I'll adjust it for you."
)


class PresentPlanUpdate(TypedDict):
    """The state ``present_plan`` writes."""

    messages: list[AnyMessage]


async def build_plan_message(plan: dict | None) -> str:
    """Compose the one message a verified plan is shown to the user as."""

    if not plan:
        return f"{PLAN_READY_MESSAGE}\n\n{PLAN_REVIEW_ASK}"

    markdown = await render_plan_markdown(TrainingPlan.model_validate(plan))
    intro = plan.get("summary") or PLAN_READY_MESSAGE
    return f"{intro}\n\n{markdown}\n\n{PLAN_REVIEW_ASK}"


async def present_plan(state: GraphState) -> PresentPlanUpdate:
    """Record the plan the user is about to be asked to approve."""

    return {
        "messages": [AIMessage(content=await build_plan_message(state.get("plan")))]
    }
