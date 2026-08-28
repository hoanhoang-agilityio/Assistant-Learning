"""The ``hitl_agent`` node: pause for the caller's approve/reject decision on a pending approval."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.core.configs.config import settings
from src.enums import HitlAgentRoute
from src.schemas import ApprovalDecision, GraphState

HITL_AGENT_INTERRUPT = "hitl_agent"


class HitlAgentInterrupt(TypedDict):
    """The payload the caller receives while the run is suspended here."""

    type: str
    summary: str


class HitlAgentUpdate(TypedDict):
    """The state ``hitl_agent`` writes once the caller responds."""

    approval_decision: ApprovalDecision
    approval_feedback: str | None
    approval_retry_count: int
    messages: list[AnyMessage]


def _parse_decision(reply: Any) -> tuple[ApprovalDecision, str | None]:
    """Read the caller's resume value as a decision plus the feedback text, if any."""

    if isinstance(reply, dict):
        decision: ApprovalDecision = (
            "approve" if reply.get("decision") == "approve" else "reject"
        )
        return decision, reply.get("feedback") or None

    text = str(reply).strip()
    if text.lower() in {"approve", "approved", "yes"}:
        return "approve", None
    return "reject", text or None


async def hitl_agent(state: GraphState) -> HitlAgentUpdate:
    """Pause the graph and record the caller's approve/reject decision on the pending approval."""

    summary = state["pending_approval"]["summary"]
    reply = interrupt(HitlAgentInterrupt(type=HITL_AGENT_INTERRUPT, summary=summary))

    decision, feedback = _parse_decision(reply)

    retry_count = state.get("approval_retry_count", 0)
    if decision == "reject" and feedback:
        retry_count += 1

    return {
        "approval_decision": decision,
        "approval_feedback": feedback,
        "approval_retry_count": retry_count,
        "messages": [HumanMessage(content=feedback or decision)],
    }


def route_after_hitl(state: GraphState) -> HitlAgentRoute:
    """Dispatch on the pending approval's source and the caller's decision, to one of six outcomes."""

    decision = state.get("approval_decision")

    if state["pending_approval"]["source"] == "user_agent":
        if decision == "approve":
            return HitlAgentRoute.USER_APPROVE
        return HitlAgentRoute.USER_REJECT

    if decision != "reject":
        return HitlAgentRoute.COACH_APPROVE
    if not state.get("approval_feedback"):
        return HitlAgentRoute.COACH_NO_FEEDBACK
    if state.get("approval_retry_count", 0) >= settings.HITL_MAX_RETRIES:
        return HitlAgentRoute.COACH_EXHAUSTED
    return HitlAgentRoute.COACH_REVISE
