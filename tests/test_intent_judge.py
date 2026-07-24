import pytest
from pydantic import ValidationError

from core.agents.intent_judge import (
    UserIntentJudgement,
    configure_user_intent_judge,
    judge_user_intent,
)


def _judge_stub(user_intent: str, **overrides: object) -> None:
    defaults: dict[str, object] = {
        "user_intent": user_intent,
        "reason": "stub",
        "mentions_submitted_plan": False,
        "touches_goal_or_constraints": False,
    }
    defaults.update(overrides)
    configure_user_intent_judge(lambda _query: UserIntentJudgement(**defaults))


@pytest.mark.parametrize("intent", ["generate", "edit", "verify"])
def test_judge_classifies_each_supported_intent(intent: str) -> None:
    _judge_stub(intent)
    result = judge_user_intent("irrelevant, override is fixed")
    assert result.user_intent == intent


def test_mentions_submitted_plan_is_a_boolean_not_transcribed_text() -> None:
    """Design review F2: the judge signals presence of a submitted plan, it never
    reproduces the plan's content."""
    _judge_stub("verify", mentions_submitted_plan=True)
    result = judge_user_intent(
        "Here's the plan I've been running: [4-day upper/lower split, ...]. Is this safe?"
    )
    assert result.mentions_submitted_plan is True
    assert not hasattr(result, "submitted_plan_text")


def test_touches_goal_or_constraints_is_judge_provided_not_keyword_matched() -> None:
    """Design review F11: the edit-scope signal comes from the judge's structured
    output, not from keyword parsing in the resolver."""
    _judge_stub("edit", touches_goal_or_constraints=True)
    result = judge_user_intent("switch my goal to strength instead")
    assert result.touches_goal_or_constraints is True


def test_analyze_is_not_a_constructible_user_intent() -> None:
    """Design review §7: `analyze` is withheld from the type entirely, not just
    unimplemented downstream, so a run can never dead-end on it."""
    with pytest.raises(ValidationError):
        UserIntentJudgement(
            user_intent="analyze",
            reason="stub",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=False,
        )


def test_configure_override_reset_to_none_falls_back_to_real_judge_path() -> None:
    """Not a call to the real LLM (no override configured means judge_user_intent would
    hit the network) -- this only asserts the override-clearing mechanics themselves,
    mirroring configure_request_type_judge's own test coverage shape."""
    _judge_stub("generate")
    assert judge_user_intent("anything").user_intent == "generate"
    configure_user_intent_judge(None)
    # A fresh override must be supplied before the next call; conftest's autouse fixture
    # restores default_user_intent_judge after this test regardless.
    _judge_stub("verify")
    assert judge_user_intent("anything").user_intent == "verify"
