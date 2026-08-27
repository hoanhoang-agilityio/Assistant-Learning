"""The ``hitl_review`` node: pause for the user's approve/reject decision on the plan."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.core.configs.config import settings
from src.core.langgraph.nodes.present_plan import PLAN_REVIEW_ASK
from src.enums import HitlRoute
from src.schemas import (
    GraphState,
    HitlDecision,
)

HITL_REVIEW_INTERRUPT = "hitl_review"


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
            message=PLAN_REVIEW_ASK,
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
