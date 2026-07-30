from typing import Any

from core.orchestration.agents.state import ApprovalStatus


def request_approval_data(draft_plan: str, verification_report: dict[str, Any]) -> dict[str, Any]:
    passed = verification_report.get("passed", False)
    return {
        "waiting_for_user": True,
        "approval_status": "pending",
        "hitl_type": "approval",
        "message": (
            "Review the draft fitness plan. Approve to save, reject to cancel, "
            "or request changes with feedback to replan."
        ),
        "verification_passed": passed,
        "draft_preview": draft_plan[:500],
    }


def classify_approval_response(user_response: str, *, strict: bool) -> ApprovalStatus:
    """Classify free-text approve/reject/revision phrasing.

    `strict=False` (used by `hitl_control_data`, the live tool-approval flow) also matches
    any `startswith("approve")`/`startswith("reject")` prefix. `strict=True` (used by
    `resume_run`'s free-text path) only matches the exact phrase sets -- kept separate rather
    than unified so each call site's existing, independently-verified behavior is preserved.
    """
    normalized = user_response.strip().lower()
    if normalized in {"approve", "approved", "yes"} or (
        not strict and normalized.startswith("approve")
    ):
        return "approved"
    if normalized in {"reject", "rejected", "no"} or (
        not strict and normalized.startswith("reject")
    ):
        return "rejected"
    return "revision_requested"


def hitl_control_data(
    waiting_for_user: bool,
    approval_status: str | None,
    user_response: str | None,
) -> dict[str, Any]:
    if not waiting_for_user:
        return {"waiting_for_user": False}

    if user_response is None:
        return {
            "waiting_for_user": True,
            "approval_status": approval_status or "pending",
        }

    return {
        "waiting_for_user": False,
        "approval_status": classify_approval_response(user_response, strict=False),
        "user_response": user_response,
    }
