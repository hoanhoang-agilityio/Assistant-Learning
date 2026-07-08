import pytest

from core.hitl.interrupt_policy import tool_requires_interrupt
from core.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    revision_to_replan_update,
    user_revision_to_replan_update,
)
from core.hitl.tool_gate import evaluate_tool_interrupt


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
    update = decision_to_resume_update(decision, replan_count=0)
    assert update["approval_status"] == "pending"
    assert update["route_decision"] == "REPLAN"
    assert "replan_count" not in update
    assert update["revision_feedback"] == "Add more leg volume."
    assert update["verification_passed"] is False
    assert update["waiting_for_user"] is False


def test_revision_to_replan_update_raises_when_exhausted() -> None:
    with pytest.raises(ValueError, match="Maximum replan attempts"):
        revision_to_replan_update("Too much cardio.", replan_count=1)


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


def test_tool_requires_interrupt_for_extract_profile() -> None:
    assert tool_requires_interrupt("extract_profile") is False
    assert tool_requires_interrupt("validate_profile") is False


def test_evaluate_tool_interrupt_skips_when_already_approved() -> None:
    result = evaluate_tool_interrupt(
        "extract_profile",
        used_sensitive_write=True,
        approved_tools=["extract_profile"],
        preview={"age": 30},
    )
    assert result is None


def test_evaluate_tool_interrupt_returns_none_when_tool_not_interruptible() -> None:
    result = evaluate_tool_interrupt(
        "extract_profile",
        used_sensitive_write=True,
        approved_tools=[],
        preview={"age": 30},
    )
    assert result is None
