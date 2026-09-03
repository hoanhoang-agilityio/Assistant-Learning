"""Tests for the ``coach_agent`` node's own routing: answer, plan, or go and collect the profile first."""

import sys

import pytest

from src.agents.coach import coach_agent, route_after_coach
from src.enums import CoachRoute
from src.schemas import GraphState, PlanAnswer, initial_state

coach_module = sys.modules[coach_agent.__module__]

USER_ID = "user-1"

COMPLETE = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}

STORED_PLAN = {"template_id": "t-1", "training_days": [{"day_number": 1}]}


def _state(profile: dict | None) -> GraphState:
    return initial_state("build me a plan", USER_ID) | {"profile": profile}


def _answering_agent(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    """Stand in for a model that read the stored plan and replied about it."""

    class _Agent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            return {"structured_response": PlanAnswer(answer=answer)}

    monkeypatch.setattr(coach_module, "build_coach_agent", _Agent)


async def test_an_incomplete_profile_is_not_sent_to_the_model() -> None:
    """No profile on record means no plan attempt at all — the model is never called,
    so the node returns without needing one."""
    result = await coach_agent(_state(None))

    assert result["plan"] is None


async def test_an_incomplete_profile_flags_the_bounce_back_to_the_supervisor() -> None:
    """The coach cannot ask ``user_agent`` for the fields itself — it can only tell the
    supervisor a plan is waiting on them, via the field the router reads."""
    result = await coach_agent(_state(None))

    assert result["profile_status"] == "need_input"


async def test_a_complete_profile_does_not_touch_the_profile_status_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once there is a plan to build, profile completeness is not this turn's concern."""

    class _FailingCoachAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(coach_module, "build_coach_agent", _FailingCoachAgent)

    result = await coach_agent(_state(COMPLETE))

    assert "profile_status" not in result


def test_an_incomplete_profile_routes_to_collection_not_verification() -> None:
    """The bug this replaced: a missing profile went to the verification gate, which
    read "no plan" as "bad plan", retried the coach against the same empty profile and
    burned the retry budget before ever asking the user for anything."""
    assert route_after_coach(_state(None)) == CoachRoute.NEEDS_PROFILE


def test_a_partial_profile_still_routes_to_collection() -> None:
    """One missing required field is as unplannable as seven."""
    partial = {name: value for name, value in COMPLETE.items() if name != "goal"}

    assert route_after_coach(_state(partial)) == CoachRoute.NEEDS_PROFILE


def test_a_complete_profile_goes_on_to_verification() -> None:
    """With everything on file the coaching branch runs exactly as it did before."""
    assert route_after_coach(_state(COMPLETE)) == CoachRoute.READY


# --- Answering about the plan on record ---------------------------------------------------


async def test_an_answer_about_the_stored_plan_is_the_turns_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read path has no plan to present, so what the agent said is what the user gets."""
    _answering_agent(monkeypatch, "You train four days: upper, lower, upper, lower.")

    result = await coach_agent(_state(COMPLETE))

    assert [message.content for message in result["messages"]] == [
        "You train four days: upper, lower, upper, lower."
    ]


async def test_an_answer_leaves_the_conversations_draft_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asking what a plan holds is not a revision of the draft being reviewed."""
    _answering_agent(monkeypatch, "Nothing is on record yet.")

    result = await coach_agent(_state(COMPLETE) | {"plan": STORED_PLAN})

    assert "plan" not in result


async def test_an_answer_skips_the_verification_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this branch exists for: a question about the plan ran the whole build
    path — gate, presentation and an approval interrupt asking the user to sign off on a
    plan they had only asked about."""
    _answering_agent(monkeypatch, "Day 2 is your lower body day.")

    result = await coach_agent(_state(COMPLETE))

    assert route_after_coach(_state(COMPLETE) | result) == CoachRoute.ANSWERED


async def test_an_empty_answer_is_not_treated_as_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routed as answered, it would end the turn having said nothing at all."""
    _answering_agent(monkeypatch, "   ")

    result = await coach_agent(_state(COMPLETE))

    assert result["coach_outcome"] == "drafted"


async def test_a_failed_attempt_does_not_route_as_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that returned neither shape still owes the gate a plan to reject."""

    class _FailingCoachAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(coach_module, "build_coach_agent", _FailingCoachAgent)

    result = await coach_agent(_state(COMPLETE))

    assert route_after_coach(_state(COMPLETE) | result) == CoachRoute.READY


async def test_a_stale_answer_does_not_route_the_next_turns_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State is checkpointed per conversation: an answer last turn would send this turn's
    plan straight past the gate."""

    class _PlanningAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            return {"structured_response": None}

    monkeypatch.setattr(coach_module, "build_coach_agent", _PlanningAgent)

    stale = _state(COMPLETE) | {"coach_outcome": "answered"}
    result = await coach_agent(stale)

    assert route_after_coach(stale | result) == CoachRoute.READY
