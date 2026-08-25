"""The HITL review loop end to end: approve, revise, stop, and exhaust the budget.

Runs the real compiled graph from a verified plan through ``hitl_review``. The coach agent
and todo writer are stubbed — their own contracts are covered in ``test_coach_agent.py`` and
``test_write_todo.py`` — everything else, including ``deterministic_verification``, runs for
real against the fixture catalogue from ``test_verification_gate.py``.
"""

import sys

import pytest
from langgraph.types import Command

import src.core.langgraph.nodes.intent as intent_node
import src.core.langgraph.verification.deterministic.context as plan_context
import src.services.profile as profile_service
from src.core.configs.config import settings
from src.core.langgraph.agents.coach import coach_agent
from src.core.langgraph.graph import build_graph
from src.core.langgraph.nodes.extract_user_info import extract_user_info
from src.core.langgraph.nodes.hitl_exhausted import HITL_EXHAUSTED_MESSAGE
from src.core.langgraph.nodes.hitl_rejected_no_feedback import (
    HITL_REJECTED_NO_FEEDBACK_MESSAGE,
)
from src.core.langgraph.nodes.write_todo import write_todo
from src.core.langgraph.runtime import MemoryScope, namespace_for
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import initial_state
from src.services import plan_presentation
from src.services.profile import PROFILE_KEY, ProfileExtraction
from tests.test_verification_completeness import CATALOGUE, TEMPLATE
from tests.test_verification_gate import PROFILE, passing_plan

coach_module = sys.modules[coach_agent.__module__]
todo_node = sys.modules[write_todo.__module__]
extract_node = sys.modules[extract_user_info.__module__]

USER_ID = "user-hitl-loop"
CONFIG = {"configurable": {"thread_id": "hitl-loop"}}

TASKS = ["Return the complete plan."]


class _StubAgent:
    """Stands in for the compiled coach agent: always the same plan, whatever it is shown."""

    def __init__(self) -> None:
        self.seen_messages: list = []

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.seen_messages = inputs["messages"]
        return {"messages": [], "structured_response": passing_plan()}


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The real graph, primed with a complete profile and a plan that clears the gate."""

    async def classify_as_coaching(_: str) -> str:
        return "coaching"

    async def extract_nothing(
        _: str, fields_in_focus: list[str] | None = None
    ) -> ProfileExtraction:
        return ProfileExtraction()

    async def fetch_template(template_id: str):
        return TEMPLATE if template_id == TEMPLATE.id else None

    async def fetch_exercises_by_id(exercise_ids: list[str]):
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    async def write_tasks(**kwargs: object) -> list[str]:
        return TASKS

    runtime = InMemoryRuntime()
    monkeypatch.setattr(profile_service, "graph_runtime", runtime)
    monkeypatch.setattr(intent_node, "classify_user_intent", classify_as_coaching)
    monkeypatch.setattr(extract_node, "extract_profile_fields", extract_nothing)
    monkeypatch.setattr(plan_context, "fetch_template", fetch_template)
    monkeypatch.setattr(plan_context, "fetch_exercises_by_id", fetch_exercises_by_id)
    monkeypatch.setattr(plan_presentation, "fetch_exercises_by_id", fetch_exercises_by_id)
    monkeypatch.setattr(todo_node, "generate_todo", write_tasks)

    agent = _StubAgent()
    monkeypatch.setattr(coach_module, "build_coach_agent", lambda: agent)

    store = await runtime.store()
    await store.aput(
        namespace_for(USER_ID, MemoryScope.FACTS),
        PROFILE_KEY,
        PROFILE.model_dump(mode="json"),
    )

    graph = build_graph().compile(
        checkpointer=await runtime.checkpointer(), name="hitl_loop_test"
    )
    graph.agent = agent
    yield graph
    await runtime.close()


async def _start(loop) -> dict:
    """Drive a fresh run up to the review gate."""
    return await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)


async def test_the_run_suspends_at_review_once_the_plan_clears_the_gate(loop) -> None:
    """Verification passing is what opens the review gate, not what ends the run."""
    suspended = await _start(loop)

    assert "__interrupt__" in suspended
    assert (await loop.aget_state(CONFIG)).next == ("hitl_review",)


async def test_an_approval_ends_the_run_with_the_plan(loop) -> None:
    """Approving is the only path that hands the plan back as-is."""
    await _start(loop)

    result = await loop.ainvoke(Command(resume="approve"), CONFIG)

    assert result["hitl_decision"] == "approve"
    assert result["plan"] == passing_plan().model_dump()
    assert (await loop.aget_state(CONFIG)).next == ()


async def test_a_rejection_with_feedback_sends_the_plan_back_for_revision(loop) -> None:
    """Feedback reaches the coach agent, and the revised plan is reviewed again."""
    await _start(loop)

    resumed = await loop.ainvoke(
        Command(resume={"decision": "reject", "feedback": "too much volume on day 1"}),
        CONFIG,
    )

    assert "__interrupt__" in resumed
    assert resumed["hitl_retry_count"] == 1
    assert "too much volume on day 1" in str(loop.agent.seen_messages[-1].content)
    assert (await loop.aget_state(CONFIG)).next == ("hitl_review",)


async def test_a_rejection_with_no_feedback_stops_the_run(loop) -> None:
    """Nothing to revise from ends the run instead of looping back to the coach."""
    await _start(loop)

    resumed = await loop.ainvoke(Command(resume={"decision": "reject"}), CONFIG)

    assert resumed["final_message"] == HITL_REJECTED_NO_FEEDBACK_MESSAGE
    assert (await loop.aget_state(CONFIG)).next == ()


async def test_the_revision_loop_is_bounded(loop) -> None:
    """Without the counter this loop never terminates: review, revise, review again."""
    result = await _start(loop)
    reviews = 1

    while "__interrupt__" in result:
        result = await loop.ainvoke(
            Command(resume={"decision": "reject", "feedback": "still not right"}),
            CONFIG,
        )
        reviews += "__interrupt__" in result

    assert reviews == settings.HITL_MAX_RETRIES
    assert result["hitl_retry_count"] == settings.HITL_MAX_RETRIES
    assert result["final_message"] == HITL_EXHAUSTED_MESSAGE
    assert (await loop.aget_state(CONFIG)).next == ()
