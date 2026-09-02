"""Collecting a profile end to end: the run stops, asks once, and plans from the answer.

The regression this pins down is the loop it replaced. A user asking for a plan with
nothing on file used to reach ``coach_agent``, come back with no plan, and be sent to the
deterministic gate — which reads "no plan" as "bad plan", counted a retry and sent the
coach back at the same empty profile until the budget ran out, without ever asking the
user for anything. What has to happen instead is a single pause with a form on it.

Profile collection now lives on the ``user_agent`` branch rather than hanging off
``coach_agent`` directly: the coach flags what it is missing and bounces back to the
supervisor (via ``profile_required_for``/``profile_status``), and the supervisor is the
one that sends the turn on to ``user_agent`` — which is what actually reaches
``draft_profile``/``collect_profile``. The supervisor stub below reads the same
``profile_status`` line the real prompt now carries, so it drives the same two-hop
handoff a real model would, however many times a test resumes or restarts the run.
"""

import sys
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command

import src.agents.coach as coach_module
import src.agents.user as user_module
import src.nodes.verification as verification_module
import src.services.memory as memory_service
from src.agents.supervisor import SupervisorDecision, supervisor
from src.graph import build_graph
from src.nodes import PROFILE_FORM_INTERRUPT
from src.nodes.draft_profile import draft_profile
from src.nodes.present_plan import present_plan
from src.runtime import MemoryScope, namespace_for
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import VerificationResult, initial_state
from src.services.profile import PROFILE_KEY
from tests.test_verification_completeness import complete_plan

supervisor_module = sys.modules[supervisor.__module__]
present_plan_module = sys.modules[present_plan.__module__]
draft_module = sys.modules[draft_profile.__module__]

USER_ID = "user-profile-collection"
CONFIG = {"configurable": {"thread_id": "profile-collection"}}

QUERY = (
    "I'd like a training plan. I'm 27, male, 178 cm, 80 kg, aiming for 75 kg. "
    "I train 4 days a week at a gym and I'm moderately active."
)

STATED = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "target_weight_kg": 75.0,
    "training_days_per_week": 4,
}

# What the user fills the rest of the form in with.
COMPLETED = {**STATED, "activity_level": "MODERATE", "goal": "FAT_LOSS"}

PLAN = complete_plan()


class _StubCoachAgent:
    """Stands in for the compiled coach agent: one already-valid plan, every time."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.calls += 1
        return {"messages": [], "structured_response": PLAN}


class _StubUserAgent:
    """Stands in for the compiled user agent: no tool calls of its own.

    ``draft_profile`` is what actually pulls the stated facts out of the conversation;
    the user agent's own turn only has to happen and hand off, not extract anything.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.calls += 1
        return {"messages": []}


class _StatusAwareSupervisor:
    """Routes on the ``profile_status`` line the real prompt now carries.

    A fixed, hand-counted decision list would have to know in advance how many times a
    test resumes or restarts the run; reading the same context a real model would see
    instead makes the stub correct for any number of hops.
    """

    def with_retry(self, **_: object) -> "_StatusAwareSupervisor":
        return self

    async def ainvoke(self, messages: list) -> SupervisorDecision:
        for message in messages:
            content = getattr(message, "content", "")
            if content == "profile_status: need_input":
                return SupervisorDecision(next="user_agent")
            if content == "profile_status: ready":
                return SupervisorDecision(next="coach_agent")
        return SupervisorDecision(next="coach_agent")


class _FakeChatModel:
    def __init__(self, structured: object) -> None:
        self.structured = structured

    def with_structured_output(self, _schema: type) -> object:
        return self.structured


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The real graph with an empty profile store and every model call under test control."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)

    async def verify_plan(*_args: object, **_kwargs: object) -> VerificationResult:
        return VerificationResult(issues=[])

    monkeypatch.setattr(verification_module, "verify_plan", verify_plan)

    async def render_plan_markdown(_plan: object) -> str:
        return "Your training plan is ready."

    monkeypatch.setattr(
        present_plan_module, "render_plan_markdown", render_plan_markdown
    )

    # The extraction itself is covered in ``test_profile_draft.py``; here it only has to
    # return what the user's opening message plainly stated.
    async def read_draft(_messages: list) -> dict:
        return dict(STATED)

    monkeypatch.setattr(draft_module, "read_draft", read_draft)

    coach_agent = _StubCoachAgent()
    user_agent = _StubUserAgent()
    monkeypatch.setattr(coach_module, "build_coach_agent", lambda: coach_agent)
    monkeypatch.setattr(user_module, "build_user_agent", lambda: user_agent)
    monkeypatch.setattr(
        supervisor_module,
        "chat_model",
        lambda **_: _FakeChatModel(_StatusAwareSupervisor()),
    )

    graph = build_graph().compile(
        checkpointer=await runtime.checkpointer(), name="profile_collection_test"
    )
    graph.coach_agent = coach_agent
    graph.user_agent = user_agent
    graph.store = await runtime.store()

    yield graph
    await runtime.close()


async def _ask(graph) -> dict[str, Any]:
    """Ask for a plan with nothing on file, and run until the graph stops."""
    return await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)


def _form(result: dict[str, Any]) -> dict[str, Any]:
    return result["__interrupt__"][0].value


# --- The pause ----------------------------------------------------------------------------


async def test_a_missing_profile_stops_the_run_and_asks(loop) -> None:
    """The run parks on a form instead of running itself out of retries in silence."""
    result = await _ask(loop)

    assert _form(result)["type"] == PROFILE_FORM_INTERRUPT


async def test_the_coach_is_not_retried_against_an_empty_profile(loop) -> None:
    """The loop itself: the coach must not be sent back at a profile that cannot have
    changed, and the retry budget must be untouched when the run stops to ask."""
    result = await _ask(loop)

    assert loop.coach_agent.calls == 0
    assert result.get("coach_retry_count", 0) == 0


async def test_the_form_asks_only_for_what_the_user_did_not_say(loop) -> None:
    """The complaint this answers: being asked for all seven fields right after
    supplying five of them."""
    fields = _form(await _ask(loop))["fields"]

    assert {field["name"] for field in fields} >= {"activity_level", "goal"}
    assert _form(await _ask(loop))["values"]["age"] == 27


# --- The answer ---------------------------------------------------------------------------


async def test_a_completed_form_is_saved_once_and_the_plan_is_built(loop) -> None:
    """One write for the whole profile, then straight on to the plan the user asked for."""
    await _ask(loop)

    result = await loop.ainvoke(Command(resume=COMPLETED), CONFIG)

    stored = await loop.store.aget(
        namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY
    )
    assert stored.value["goal"] == "FAT_LOSS"
    assert stored.value["age"] == 27
    assert loop.coach_agent.calls == 1
    assert result["pending_approval"]["kind"] == "plan"


async def test_the_stated_fields_survive_the_round_trip(loop) -> None:
    """What the user typed in their first message must end up on file, not be dropped
    because the form only collected what was missing from it."""
    await _ask(loop)

    result = await loop.ainvoke(Command(resume=COMPLETED), CONFIG)

    assert result["profile"]["target_weight_kg"] == 75.0
    assert result["profile"]["training_days_per_week"] == 4


async def test_an_incomplete_form_asks_again_without_reaching_the_coach(loop) -> None:
    """Every required field is verified before anything is stored or planned."""
    await _ask(loop)

    result = await loop.ainvoke(Command(resume={"age": 27}), CONFIG)

    assert _form(result)["errors"]
    assert loop.coach_agent.calls == 0


async def test_the_conversation_says_what_happened(loop) -> None:
    """The user is told the profile was taken before the plan turns up."""
    await _ask(loop)

    result = await loop.ainvoke(Command(resume=COMPLETED), CONFIG)
    said = [
        message.content
        for message in result["messages"]
        if isinstance(message, AIMessage)
    ]

    assert any("everything I need" in text for text in said)
