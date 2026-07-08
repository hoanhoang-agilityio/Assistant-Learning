from typing import Any

from core.profile.labels import format_missing_profile_prompt


def request_clarification_data(missing_fields: list[str], context: str) -> dict[str, Any]:
    message = format_missing_profile_prompt(missing_fields)
    if context:
        message = f"{message} Context: {context}"
    return {
        "waiting_for_user": True,
        "approval_status": "pending",
        "hitl_type": "clarification",
        "message": message,
        "missing_fields": missing_fields,
    }


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

    response_lower = user_response.strip().lower()
    if response_lower in {"approve", "approved", "yes"} or response_lower.startswith("approve"):
        return {
            "waiting_for_user": False,
            "approval_status": "approved",
            "user_response": user_response,
        }
    if response_lower in {"reject", "rejected", "no"} or response_lower.startswith("reject"):
        return {
            "waiting_for_user": False,
            "approval_status": "rejected",
            "user_response": user_response,
        }
    return {
        "waiting_for_user": False,
        "approval_status": "revision_requested",
        "user_response": user_response,
    }
