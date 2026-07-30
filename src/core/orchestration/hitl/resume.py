from typing import Any, Literal

from core.orchestration.agents.state import ApprovalStatus

HitlDecisionType = Literal["approve", "reject", "revision"]
MAX_REVISION_COUNT = 1


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
    stripped = feedback.strip()
    if not stripped:
        raise ValueError("message is required")
    if revision_count >= MAX_REVISION_COUNT:
        raise ValueError(
            f"Maximum number of plan revisions ({MAX_REVISION_COUNT}) already used for this run."
        )
    return {
        "revision_feedback": stripped,
        "revision_count": revision_count + 1,
        # Left as "revision_requested" (not reset to "pending") -- the Policy
        # Engine's revision_requested rule (core.orchestration.routing.policy_engine) is
        # what routes this to Fitness once the graph re-enters Supervisor; it reads
        # this exact field.
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
