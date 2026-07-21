import pytest

from core.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    user_revision_to_replan_update,
)


def test_create_approval_decision_approve() -> None:
    decision = create_approval_decision("approve")
    assert decision["approval_status"] == "approved"
    assert decision_to_resume_update(decision)["waiting_for_user"] is False


def test_create_approval_decision_reject_requires_message() -> None:
    with pytest.raises(ValueError, match="message is required"):
        create_approval_decision("reject")


def test_create_approval_decision_revision_requires_message() -> None:
    with pytest.raises(ValueError, match="message is required"):
        create_approval_decision("revision")


def test_create_approval_decision_revision_triggers_replan() -> None:
    decision = create_approval_decision("revision", message="Add more leg volume.")
    update = decision_to_resume_update(decision)
    assert update["approval_status"] == "pending"
    assert update["route_decision"] == "REPLAN"
    assert "replan_count" not in update
    assert update["revision_feedback"] == "Add more leg volume."
    assert update["verification_passed"] is False
    assert update["waiting_for_user"] is False


def test_user_revision_to_replan_update_allows_repeat_requests() -> None:
    first = user_revision_to_replan_update("train 3 days per week")
    second = user_revision_to_replan_update("train 3 days per week again")
    assert first["route_decision"] == "REPLAN"
    assert second["route_decision"] == "REPLAN"
    assert "replan_count" not in first
    assert "replan_count" not in second


def test_create_approval_decision_tool_resume_merges_approved_tools() -> None:
    decision = create_approval_decision(
        "approve",
        pending_tool="extract_profile",
        approved_tools=[],
    )
    update = decision_to_resume_update(decision)
    assert update["approved_tools"] == ["extract_profile"]
    assert update["pending_tool"] is None
