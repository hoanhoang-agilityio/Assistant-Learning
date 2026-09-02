"""Tests for ``build_coach_input``'s ``<slots_to_fix>`` narrowing.

The gap this closes: a verification retry names its slots from structured issues, but a
HITL reviewer's rejection is free text with no such structure. Left alone, the coach saw
no ``<slots_to_fix>`` tag at all on that branch and fell back to looking up every slot in
the plan for a change that touches one of them.
"""

from src.agents.coach import build_coach_input
from src.prompts.coach_agent import NO_SLOTS_TO_FIX, REVIEWER_SLOTS_TO_FIX
from src.schemas import GraphState, initial_state

USER_ID = "user-1"


def _content(state: GraphState) -> str:
    return build_coach_input(state)[-1].content


def _state(**overrides: object) -> GraphState:
    return initial_state("build me a plan", USER_ID) | overrides


def test_a_first_attempt_carries_no_slots_to_fix_tag() -> None:
    """Nothing to narrow yet — every slot in a brand new plan is fair game."""
    assert "<slots_to_fix>" not in _content(_state())


def test_a_verification_retry_lists_its_own_slots() -> None:
    """Structured issues give an exact list, so the model is told exactly that."""
    verification = {
        "issues": [
            {"severity": "error", "day_number": 1, "slot_id": "d1_s1"},
        ]
    }

    content = _content(_state(verification_result=verification))

    assert "<slots_to_fix>" in content
    assert "d1_s1" in content
    assert REVIEWER_SLOTS_TO_FIX not in content


def test_a_verification_retry_with_no_error_slots_says_so() -> None:
    """A retry with nothing flagged must not be read as free rein over the whole plan."""
    content = _content(_state(verification_result={"issues": []}))

    assert NO_SLOTS_TO_FIX in content


def test_a_reviewer_rejection_is_told_to_find_its_own_slot() -> None:
    """No structured slot exists for free text, so the model is pointed at the feedback
    and the current plan instead of being left to fall back to looking up everything."""
    content = _content(_state(approval_feedback="swap the bench press"))

    assert "<slots_to_fix>" in content
    assert REVIEWER_SLOTS_TO_FIX in content


def test_a_verification_retry_takes_priority_over_leftover_feedback() -> None:
    """Both fields can be set on a plan revised more than once; the structured signal
    from the current attempt is the one that actually narrows the lookup."""
    verification = {
        "issues": [{"severity": "error", "day_number": 1, "slot_id": "d1_s1"}]
    }

    content = _content(
        _state(verification_result=verification, approval_feedback="swap it")
    )

    assert "d1_s1" in content
    assert REVIEWER_SLOTS_TO_FIX not in content
