"""The ``plan_approval`` node: pause for the coach's reviewer to approve or reject a plan."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.configs.config import settings
from src.enums import PlanApprovalRoute
from src.schemas import ApprovalDecision, GraphState

PLAN_APPROVAL_INTERRUPT = "plan_approval"


class PlanApprovalInterrupt(TypedDict):
    """The payload the caller receives while the run is suspended here."""

    type: str
    summary: str


class PlanApprovalUpdate(TypedDict):
    """The state ``plan_approval`` writes once the caller responds."""

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


async def plan_approval(state: GraphState) -> PlanApprovalUpdate:
    """Pause the graph and record the caller's approve/reject decision on the pending plan."""

    summary = state["pending_approval"]["summary"]
    reply = interrupt(
        PlanApprovalInterrupt(type=PLAN_APPROVAL_INTERRUPT, summary=summary)
    )

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


def route_after_plan_approval(state: GraphState) -> PlanApprovalRoute:
    """Dispatch on the reviewer's decision, to one of four outcomes."""

    decision = state.get("approval_decision")

    if decision != "reject":
        return PlanApprovalRoute.COACH_APPROVE
    if not state.get("approval_feedback"):
        return PlanApprovalRoute.COACH_NO_FEEDBACK
    if state.get("approval_retry_count", 0) >= settings.HITL_MAX_RETRIES:
        return PlanApprovalRoute.COACH_EXHAUSTED
    return PlanApprovalRoute.COACH_REVISE
