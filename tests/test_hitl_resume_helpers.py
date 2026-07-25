import pytest

from core.agents.rerun import MAX_REPLAN_COUNT
from core.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    user_revision_to_replan_update,
)


def test_create_approval_decision_approve() -> None:
    decision = create_approval_decision("approve")
    assert decision["approval_status"] == "approved"
    assert decision_to_resume_update(decision, replan_count=0)["waiting_for_user"] is False


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
    # Regression (PR8): the user-initiated revision path must increment the same
    # replan_count/MAX_REPLAN_COUNT budget the AI-auto-replan path already enforces
    # -- previously this key was never present here at all, so a user could
    # request unlimited revisions with no bound.
    assert update["replan_count"] == 1
    assert update["revision_feedback"] == "Add more leg volume."
    assert update["verification_passed"] is False
    assert update["waiting_for_user"] is False


def test_user_revision_to_replan_update_increments_the_shared_replan_counter() -> None:
    """Regression (PR8): a call increments replan_count from whatever the
    caller currently holds -- the same counter/cap partial_rerun_decision_data
    (the AI-auto-replan path) already enforces, not a separate, unbounded one."""
    result = user_revision_to_replan_update("train 3 days per week", replan_count=0)

    assert result["route_decision"] == "REPLAN"
    assert result["replan_count"] == 1


def test_user_revision_to_replan_update_rejects_once_the_shared_budget_is_exhausted() -> None:
    """Regression (PR8): the core bug this PR closes. Once replan_count has
    reached MAX_REPLAN_COUNT, a further user-initiated revision request must be
    rejected (ValueError, mapped to 409 Conflict by the API layer) rather than
    silently incrementing past the cap forever."""
    with pytest.raises(ValueError, match="Maximum number of plan revisions"):
        user_revision_to_replan_update("one more change", replan_count=MAX_REPLAN_COUNT)


def test_decision_to_resume_update_rejects_revision_once_budget_is_exhausted() -> None:
    """Same guarantee through the create_approval_decision/decision_to_resume_update
    path used by resume_run's decision_type='revision' branch."""
    decision = create_approval_decision("revision", message="Add more leg volume.")

    with pytest.raises(ValueError, match="Maximum number of plan revisions"):
        decision_to_resume_update(decision, replan_count=MAX_REPLAN_COUNT)
