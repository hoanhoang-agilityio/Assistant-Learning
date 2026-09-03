"""Tests for the ``coach_agent`` node's own routing: answer, plan, or go and collect the profile first."""

import sys

import pytest

from src.agents.coach import coach_agent, route_after_coach
from src.enums import CoachRoute
from src.schemas import GraphState, NeedsProfile, PlanAnswer, initial_state
from tests.test_verification_completeness import complete_plan

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

PLAN = complete_plan()


def _state() -> GraphState:
    return initial_state("build me a plan", USER_ID)


def _stub_profile(monkeypatch: pytest.MonkeyPatch, profile: dict | None) -> None:
    """Stand in for the store read ``coach_agent`` opens with."""

    async def load_profile(_user_id: str) -> dict | None:
        return profile

    monkeypatch.setattr(coach_module, "load_profile", load_profile)


def _agent_returning(monkeypatch: pytest.MonkeyPatch, response: object) -> None:
    """Stand in for a model whose turn produced one structured response."""

    class _Agent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            return {"structured_response": response}

    monkeypatch.setattr(coach_module, "build_coach_agent", _Agent)


def _failing_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingCoachAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(coach_module, "build_coach_agent", _FailingCoachAgent)


# --- A read needs no profile, so it always reaches the model ------------------------------


async def test_a_question_about_the_plan_reaches_the_model_with_no_profile_on_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this replaces: any coach turn at all was blocked on a complete profile,
    including one that never needed it — asking what the stored plan holds does not."""
    _stub_profile(monkeypatch, None)
    _agent_returning(monkeypatch, PlanAnswer(answer="Nothing is on record yet."))

    result = await coach_agent(_state())

    assert result["coach_outcome"] == "answered"


def test_an_answer_is_trusted_over_an_incomplete_profile() -> None:
    """A profile missing required fields is irrelevant to a question the model could
    already answer from ``get_plan`` alone."""
    assert route_after_coach({"coach_outcome": "answered"}) == CoachRoute.ANSWERED


# --- A build or revise attempt against an incomplete profile is not trusted ---------------


async def test_the_model_still_runs_against_an_incomplete_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whether the request needs a profile is not knowable before the model has read it,
    so a build attempt is not blocked ahead of time the way it once was."""
    calls = 0
    _stub_profile(monkeypatch, None)

    class _Agent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            nonlocal calls
            calls += 1
            return {"structured_response": NeedsProfile(missing_fields=["goal"])}

    monkeypatch.setattr(coach_module, "build_coach_agent", _Agent)

    await coach_agent(_state())

    assert calls == 1


async def test_the_models_own_needs_profile_answer_is_not_treated_as_a_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model's own signal that it lacks what it needs is not a failed plan attempt to
    retry against verification — it is the same bounce a missing profile always was."""
    _stub_profile(monkeypatch, None)
    _agent_returning(monkeypatch, NeedsProfile(missing_fields=["goal"]))

    result = await coach_agent(_state())

    assert result["plan"] is None
    assert result["profile_status"] == "need_input"


async def test_a_training_plan_over_an_incomplete_profile_is_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that ignored the instruction and returned a ``TrainingPlan`` anyway is
    caught by the same deterministic check — producing the right shape does not earn it
    the verification gate's trust."""
    _stub_profile(monkeypatch, None)
    _agent_returning(monkeypatch, PLAN)

    result = await coach_agent(_state())

    assert result["plan"] is None
    assert result["profile_status"] == "need_input"


def test_an_incomplete_profile_routes_to_collection_not_verification() -> None:
    """The bug this replaced: a missing profile went to the verification gate, which
    read "no plan" as "bad plan", retried the coach against the same empty profile and
    burned the retry budget before ever asking the user for anything."""
    assert (
        route_after_coach({"coach_outcome": "needs_profile"})
        == CoachRoute.NEEDS_PROFILE
    )


async def test_a_complete_profile_does_not_touch_the_profile_status_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once there is a plan to build, profile completeness is not this turn's concern."""
    _stub_profile(monkeypatch, COMPLETE)
    _failing_agent(monkeypatch)

    result = await coach_agent(_state())

    assert "profile_status" not in result


def test_a_complete_profile_goes_on_to_verification() -> None:
    """With everything on file the coaching branch runs exactly as it did before."""
    assert route_after_coach({"coach_outcome": "drafted"}) == CoachRoute.READY


# --- Answering about the plan on record ---------------------------------------------------


async def test_an_answer_about_the_stored_plan_is_the_turns_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read path has no plan to present, so what the agent said is what the user gets."""
    _stub_profile(monkeypatch, COMPLETE)
    _agent_returning(
        monkeypatch,
        PlanAnswer(answer="You train four days: upper, lower, upper, lower."),
    )

    result = await coach_agent(_state())

    assert [message.content for message in result["messages"]] == [
        "You train four days: upper, lower, upper, lower."
    ]


async def test_an_answer_leaves_the_conversations_draft_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asking what a plan holds is not a revision of the draft being reviewed."""
    _stub_profile(monkeypatch, COMPLETE)
    _agent_returning(monkeypatch, PlanAnswer(answer="Nothing is on record yet."))

    result = await coach_agent(_state() | {"plan": STORED_PLAN})

    assert "plan" not in result


async def test_an_answer_skips_the_verification_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this branch exists for: a question about the plan ran the whole build
    path — gate, presentation and an approval interrupt asking the user to sign off on a
    plan they had only asked about."""
    _stub_profile(monkeypatch, COMPLETE)
    _agent_returning(monkeypatch, PlanAnswer(answer="Day 2 is your lower body day."))

    result = await coach_agent(_state())

    assert route_after_coach(result) == CoachRoute.ANSWERED


async def test_an_empty_answer_is_not_treated_as_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routed as answered, it would end the turn having said nothing at all."""
    _stub_profile(monkeypatch, COMPLETE)
    _agent_returning(monkeypatch, PlanAnswer(answer="   "))

    result = await coach_agent(_state())

    assert result["coach_outcome"] == "drafted"


async def test_a_failed_attempt_does_not_route_as_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that returned neither shape still owes the gate a plan to reject."""
    _stub_profile(monkeypatch, COMPLETE)
    _failing_agent(monkeypatch)

    result = await coach_agent(_state())

    assert route_after_coach(result) == CoachRoute.READY


async def test_a_stale_answer_does_not_route_the_next_turns_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State is checkpointed per conversation: an answer last turn would send this turn's
    plan straight past the gate."""
    _stub_profile(monkeypatch, COMPLETE)
    _agent_returning(monkeypatch, None)

    stale = _state() | {"coach_outcome": "answered"}
    result = await coach_agent(stale)

    assert route_after_coach(stale | result) == CoachRoute.READY
