from typing import Any, Literal

from core.orchestration.state import ApprovalStatus

HitlDecisionType = Literal["approve", "reject", "revision"]


def create_approval_decision(
    decision_type: HitlDecisionType,
    message: str | None = None,
) -> dict[str, Any]:
    if decision_type == "approve":
        return {
            "decision_type": decision_type,
            "user_response": "approve",
            "approval_status": "approved",
        }
    if decision_type == "reject":
        if not message:
            raise ValueError("message is required for 'reject' decisions")
        return {
            "decision_type": decision_type,
            "user_response": message,
            "approval_status": "rejected",
        }
    if not message:
        raise ValueError("message is required for 'revision' decisions")
    return {
        "decision_type": decision_type,
        "user_response": message,
        "approval_status": "revision_requested",
    }


def user_revision_to_replan_update(feedback: str, *, revision_count: int) -> dict[str, Any]:
    """No cap on how many times a user can request a revision -- `supervisor_max_hops`
    (core.config.settings) remains the backstop against runaway loops."""
    stripped = feedback.strip()
    if not stripped:
        raise ValueError("message is required")
    return {
        "revision_feedback": stripped,
        "revision_count": revision_count + 1,
        # Left as "revision_requested" (not reset to "pending") -- the Policy
        # Engine's revision_requested rule (core.orchestration.routing.policy_engine) is
        # what routes this through User -> Planning -> Fitness once the graph
        # re-enters Supervisor; it reads this exact field.
        "approval_status": "revision_requested",
        "verification_passed": False,
        "waiting_for_user": False,
        "active_capability": "fitness",
    }


def decision_to_resume_update(decision: dict[str, Any], *, revision_count: int) -> dict[str, Any]:
    approval_status: ApprovalStatus = decision["approval_status"]
    update: dict[str, Any] = {
        "user_response": decision["user_response"],
        "approval_status": approval_status,
        "waiting_for_user": False,
    }
    if approval_status == "revision_requested":
        update.update(
            user_revision_to_replan_update(decision["user_response"], revision_count=revision_count)
        )
    return update
