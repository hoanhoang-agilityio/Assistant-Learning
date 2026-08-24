"""The ``hitl_review`` node: pause for the user's approve/reject decision on the plan."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.schemas import GraphState, HitlDecision

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

    reply = interrupt(
        HitlReviewInterrupt(
            type=HITL_REVIEW_INTERRUPT,
            plan=state.get("plan"),
            message=HITL_REVIEW_MESSAGE,
        )
    )

    decision, feedback = _parse_decision(reply)

    return {
        "hitl_decision": decision,
        "hitl_feedback": feedback,
        "messages": [HumanMessage(content=feedback or decision)],
    }
