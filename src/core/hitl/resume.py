from typing import Any, Literal

from core.agents.state import ApprovalStatus

HitlDecisionType = Literal["approve", "reject", "revision"]


def create_approval_decision(
    decision_type: HitlDecisionType,
    message: str | None = None,
) -> dict[str, Any]:
    """Build a HITL resume decision payload for graph Command(update=...)."""
    if decision_type == "approve":
        decision: dict[str, Any] = {
            "decision_type": decision_type,
            "user_response": "approve",
            "approval_status": "approved",
        }
    elif decision_type == "reject":
        if not message:
            raise ValueError("message is required for 'reject' decisions")
        decision = {
            "decision_type": decision_type,
            "user_response": message,
            "approval_status": "rejected",
        }
    else:
        if not message:
            raise ValueError("message is required for 'revision' decisions")
        decision = {
            "decision_type": decision_type,
            "user_response": message,
            "approval_status": "revision_requested",
        }
    return decision


def user_revision_to_replan_update(feedback: str) -> dict[str, Any]:
    """Build orchestration updates for user-initiated plan changes in the same conversation."""
    stripped = feedback.strip()
    if not stripped:
        raise ValueError("message is required")
    return {
        "route_decision": "REPLAN",
        "revision_feedback": stripped,
        "approval_status": "pending",
        "verification_passed": False,
        "waiting_for_user": False,
    }


def decision_to_resume_update(decision: dict[str, Any]) -> dict[str, Any]:
    """Map a create_approval_decision payload onto orchestration state updates."""
    approval_status: ApprovalStatus = decision["approval_status"]
    update: dict[str, Any] = {
        "user_response": decision["user_response"],
        "approval_status": approval_status,
        "waiting_for_user": False,
    }
    if approval_status == "revision_requested":
        update.update(user_revision_to_replan_update(decision["user_response"]))
    return update
