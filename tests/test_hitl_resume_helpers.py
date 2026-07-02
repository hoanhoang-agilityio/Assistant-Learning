import pytest

from core.hitl.interrupt_policy import tool_requires_interrupt
from core.hitl.resume import create_approval_decision, decision_to_resume_update
from core.hitl.tool_gate import evaluate_tool_interrupt


def test_create_approval_decision_approve() -> None:
    decision = create_approval_decision("approve")
    assert decision["approval_status"] == "approved"
    assert decision_to_resume_update(decision)["waiting_for_user"] is False


def test_create_approval_decision_reject_requires_message() -> None:
    with pytest.raises(ValueError, match="message is required"):
        create_approval_decision("reject")


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
    assert tool_requires_interrupt("extract_profile") is True
    assert tool_requires_interrupt("validate_profile") is False


def test_evaluate_tool_interrupt_skips_when_already_approved() -> None:
    result = evaluate_tool_interrupt(
        "extract_profile",
        used_sensitive_write=True,
        approved_tools=["extract_profile"],
        preview={"age": 30},
    )
    assert result is None


def test_evaluate_tool_interrupt_returns_pending_payload() -> None:
    result = evaluate_tool_interrupt(
        "extract_profile",
        used_sensitive_write=True,
        approved_tools=[],
        preview={"age": 30},
    )
    assert result is not None
    assert result["pending_tool"] == "extract_profile"
    assert result["hitl_type"] == "tool_approval"
