"""Tests for the ``supervisor`` node: the routing decision, and the hop cap that bounds it."""

import sys

import pytest

from src.agents.supervisor import (
    SUPERVISOR_MAX_ITERATIONS,
    SupervisorDecision,
    route_after_supervisor,
    supervisor,
)
from src.enums import SupervisorRoute
from src.schemas import NextAgent, initial_state

supervisor_module = sys.modules[supervisor.__module__]

USER_ID = "user-1"


class _FakeStructuredModel:
    """Stands in for the structured-output call: one scripted decision, or a raised error."""

    def __init__(self, outcome: NextAgent | Exception) -> None:
        self.outcome = outcome
        self.calls = 0
        self.received: list = []

    def with_retry(self, **_: object) -> "_FakeStructuredModel":
        return self

    async def ainvoke(self, messages: list) -> SupervisorDecision:
        self.calls += 1
        self.received = messages
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SupervisorDecision(next=self.outcome)


class _FakeChatModel:
    """Stands in for ``chat_model()``: serves the one structured call the node makes."""

    def __init__(self, structured: _FakeStructuredModel) -> None:
        self.structured = structured

    def with_structured_output(self, _schema: type) -> _FakeStructuredModel:
        return self.structured


@pytest.fixture
def decides(monkeypatch: pytest.MonkeyPatch):
    """Serve a scripted routing decision instead of calling the model."""

    def use(outcome: NextAgent | Exception) -> _FakeStructuredModel:
        fake = _FakeStructuredModel(outcome)
        monkeypatch.setattr(
            supervisor_module, "chat_model", lambda **_: _FakeChatModel(fake)
        )
        return fake

    return use


def _state(**overrides: object) -> dict:
    """A run in progress, with the supervisor about to take its turn."""
    return initial_state("build me a plan and answer a question", USER_ID) | overrides


# --- The routing decision ------------------------------------------------------------------


async def test_the_models_decision_becomes_next(decides) -> None:
    """The whole point of the node: whatever the model decides is what the graph runs next."""
    decides("qa_agent")

    result = await supervisor(_state())

    assert result["next"] == "qa_agent"


@pytest.mark.parametrize("outcome", ["user_agent", "coach_agent", "qa_agent", "FINISH"])
async def test_every_agent_and_finish_can_be_decided(decides, outcome: str) -> None:
    """All four routing labels the model may answer must reach the state untouched."""
    decides(outcome)

    result = await supervisor(_state())

    assert result["next"] == outcome


async def test_a_model_failure_ends_the_turn_rather_than_looping_forever(
    decides,
) -> None:
    """A broken router must not leave the run stuck with no route out."""
    decides(RuntimeError("boom"))

    result = await supervisor(_state())

    assert result["next"] == "FINISH"


# --- The iteration count -------------------------------------------------------------------


async def test_the_first_hop_starts_the_count_at_one(decides) -> None:
    """A run with no prior hops is on its first one once the supervisor runs."""
    decides("qa_agent")

    result = await supervisor(_state())

    assert result["iteration_count"] == 1


async def test_the_count_accumulates_across_hops(decides) -> None:
    """Each pass through the supervisor is one more hop, not a reset."""
    decides("coach_agent")

    result = await supervisor(_state(iteration_count=3))

    assert result["iteration_count"] == 4


async def test_a_failed_call_still_counts_the_hop(decides) -> None:
    """A hop that failed to get a decision still happened, and still counts toward the cap."""
    decides(RuntimeError("boom"))

    result = await supervisor(_state(iteration_count=2))

    assert result["iteration_count"] == 3


# --- The hop cap -----------------------------------------------------------------------------


async def test_the_cap_is_not_reached_one_hop_early(decides) -> None:
    """The model is still consulted right up to the last hop the cap allows."""
    fake = decides("coach_agent")

    result = await supervisor(_state(iteration_count=SUPERVISOR_MAX_ITERATIONS - 1))

    assert result["next"] == "coach_agent"
    assert fake.calls == 1


async def test_the_cap_forces_finish_without_consulting_the_model(decides) -> None:
    """Past the cap the model is not asked at all — an unbounded model is what the cap prevents."""
    fake = decides("coach_agent")

    result = await supervisor(_state(iteration_count=SUPERVISOR_MAX_ITERATIONS))

    assert result["next"] == "FINISH"
    assert fake.calls == 0


async def test_the_cap_still_holds_further_past_it(decides) -> None:
    """A run that overshot the cap for any reason must not slip back under it."""
    fake = decides("coach_agent")

    result = await supervisor(_state(iteration_count=SUPERVISOR_MAX_ITERATIONS + 5))

    assert result["next"] == "FINISH"
    assert fake.calls == 0


async def test_a_capped_hop_still_counts_itself(decides) -> None:
    """The count keeps climbing even once the cap has taken over, so it never looks like it reset."""
    decides("coach_agent")

    result = await supervisor(_state(iteration_count=SUPERVISOR_MAX_ITERATIONS))

    assert result["iteration_count"] == SUPERVISOR_MAX_ITERATIONS + 1


# --- The profile_status hint --------------------------------------------------------------


async def test_profile_status_reaches_the_model_when_set(decides) -> None:
    """The model routes on ``profile_status`` without the supervisor recomputing it."""
    fake = decides("user_agent")

    await supervisor(_state(profile_status="need_input"))

    assert any(
        getattr(message, "content", "") == "profile_status: need_input"
        for message in fake.received
    )


async def test_no_profile_status_line_when_it_is_unset(decides) -> None:
    """A turn with nothing profile-related going on must not fabricate a status."""
    fake = decides("qa_agent")

    await supervisor(_state())

    assert not any(
        getattr(message, "content", "").startswith("profile_status: ")
        for message in fake.received
    )


# --- Routing on the decision -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("next_agent", "expected"),
    [
        ("user_agent", SupervisorRoute.USER_AGENT),
        ("coach_agent", SupervisorRoute.COACH_AGENT),
        ("qa_agent", SupervisorRoute.QA_AGENT),
        ("FINISH", SupervisorRoute.FINISH),
    ],
)
def test_the_route_matches_the_decision(
    next_agent: str, expected: SupervisorRoute
) -> None:
    """``route_after_supervisor`` is a pure dispatch on what the node already decided."""
    state = _state(next=next_agent)

    assert route_after_supervisor(state) == expected
