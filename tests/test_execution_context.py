"""Tests for ExecutionContext and capability contracts."""

from uuid import uuid4

import pytest

from core.orchestration.agents.intent_judge import UserIntentJudgement
from core.shared.execution_context import (
    CapabilityRequest,
    CapabilityResult,
    build_execution_context,
)


def test_execution_context_is_frozen() -> None:
    ctx = build_execution_context(intent="verify_macros")
    with pytest.raises(Exception):
        ctx.intent = "build_plan"  # type: ignore[misc]


def test_build_plan_context() -> None:
    ctx = build_execution_context(intent="build_plan")
    assert ctx.execution_mode == "artifact"
    assert ctx.entry_node == "planning"
    assert ctx.requires_profile is True


def test_capability_request_has_correlation_id() -> None:
    req = CapabilityRequest(
        request_id=uuid4(),
        capability="research",
        reason="evidence",
        return_to="fitness",
    )
    assert req.request_id is not None


def test_capability_result_supports_partial() -> None:
    result = CapabilityResult(
        request_id=uuid4(),
        capability="research",
        status="partial",
        output={"evidence_summary": "partial findings", "incomplete": True},
    )
    assert result.status == "partial"


def test_intent_judgement_uses_intent_field() -> None:
    judgement = UserIntentJudgement(
        intent="build_plan",
        reason="test",
        mentions_submitted_plan=False,
        touches_goal_or_constraints=False,
    )
    assert judgement.intent == "build_plan"
