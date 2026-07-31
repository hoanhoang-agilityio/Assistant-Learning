import pytest

from core.orchestration.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    user_revision_to_replan_update,
)


def test_create_approval_decision_approve() -> None:
    decision = create_approval_decision("approve")
    assert decision["approval_status"] == "approved"
    assert decision_to_resume_update(decision, revision_count=0)["waiting_for_user"] is False


def test_create_approval_decision_reject_requires_message() -> None:
    with pytest.raises(ValueError, match="message is required"):
        create_approval_decision("reject")


def test_create_approval_decision_revision_requires_message() -> None:
    with pytest.raises(ValueError, match="message is required"):
        create_approval_decision("revision")


def test_create_approval_decision_revision_triggers_fitness_resume() -> None:
    decision = create_approval_decision("revision", message="Add more leg volume.")
    update = decision_to_resume_update(decision, revision_count=0)
    # Left as "revision_requested" (not reset to "pending") -- the Policy Engine's
    # revision_requested rule (core.orchestration.routing.policy_engine) is what routes this
    # to Fitness once the graph re-enters Supervisor; it reads this exact field.
    assert update["approval_status"] == "revision_requested"
    assert update["revision_count"] == 1
    assert update["revision_feedback"] == "Add more leg volume."
    assert update["active_capability"] == "fitness"


def test_user_revision_to_replan_update_increments_revision_counter() -> None:
    result = user_revision_to_replan_update("train 3 days per week", revision_count=0)
    assert result["revision_count"] == 1


def test_user_revision_to_replan_update_has_no_revision_count_cap() -> None:
    """Revisions are uncapped -- supervisor_max_hops is the only backstop against
    runaway loops (see core.config.settings.max_verification_retry_attempts'
    docstring for the distinction from the automatic verification-retry cap)."""
    result = user_revision_to_replan_update("one more change", revision_count=5)
    assert result["revision_count"] == 6


def test_decision_to_resume_update_has_no_revision_count_cap() -> None:
    decision = create_approval_decision("revision", message="Add more leg volume.")
    result = decision_to_resume_update(decision, revision_count=5)
    assert result["revision_count"] == 6
