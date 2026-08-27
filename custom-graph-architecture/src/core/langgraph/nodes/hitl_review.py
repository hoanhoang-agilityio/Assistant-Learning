"""The ``hitl_review`` node: pause for the user's approve/reject decision on the plan."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.core.configs.config import settings
from src.schemas import GraphState, HitlDecision, HitlRoute, TrainingPlan
from src.services.plan_presentation import render_plan_markdown

HITL_REVIEW_INTERRUPT = "hitl_review"

HITL_REVIEW_MESSAGE = (
    "Here's your plan! Take a look and let me know what you think. "
    "If you'd like anything changed, just tell me and I'll adjust it for you."
)


class HitlReviewInterrupt(TypedDict):
    """The payload the caller receives while the run is suspended here."""

    type: str
    plan: dict | None
    message: str


class HitlReviewUpdate(TypedDict):
    """The state ``hitl_review`` writes once the user responds."""

    hitl_decision: HitlDecision
    hitl_feedback: str | None
    hitl_retry_count: int
    messages: list[AnyMessage]


async def _review_message(plan: dict | None) -> str:
    """The review prompt, with the plan itself rendered ahead of it when there is one."""

    if not plan:
        return HITL_REVIEW_MESSAGE
    markdown = await render_plan_markdown(TrainingPlan.model_validate(plan))
    return f"{markdown}\n\n{HITL_REVIEW_MESSAGE}"


def _parse_decision(reply: Any) -> tuple[HitlDecision, str | None]:
    """Read the caller's resume value as a decision plus the feedback text, if any."""

    if isinstance(reply, dict):
        decision: HitlDecision = (
            "approve" if reply.get("decision") == "approve" else "reject"
        )
        return decision, reply.get("feedback") or None

    text = str(reply).strip()
    if text.lower() in {"approve", "approved", "yes"}:
        return "approve", None
    return "reject", text or None


async def hitl_review(state: GraphState) -> HitlReviewUpdate:
    """Pause the graph and record the user's approve/reject decision on the plan."""

    plan = state.get("plan")
    reply = interrupt(
        HitlReviewInterrupt(
            type=HITL_REVIEW_INTERRUPT,
            plan=plan,
            message=await _review_message(plan),
        )
    )

    decision, feedback = _parse_decision(reply)

    retry_count = state.get("hitl_retry_count", 0)
    if decision == "reject" and feedback:
        retry_count += 1

    return {
        "hitl_decision": decision,
        "hitl_feedback": feedback,
        "hitl_retry_count": retry_count,
        "messages": [HumanMessage(content=feedback or decision)],
    }


def route_after_hitl_review(state: GraphState) -> HitlRoute:
    """Send an approved plan on, a revision back to the coach, or give up."""

    if state.get("hitl_decision") != "reject":
        return HitlRoute.APPROVE
    if not state.get("hitl_feedback"):
        return HitlRoute.NO_FEEDBACK
    if state.get("hitl_retry_count", 0) >= settings.HITL_MAX_RETRIES:
        return HitlRoute.EXHAUSTED
    return HitlRoute.REVISE
