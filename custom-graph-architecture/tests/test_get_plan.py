"""Tests for the ``get_plan`` tool: the coach's read of the plan on record, and whose it is."""

import json

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage

import src.services.memory as memory_service
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import CoachContext
from src.services import plan_presentation
from src.services.memory import save_plan
from src.tools.plan import NO_PLAN_RECORDED, get_plan
from tests.test_verification_completeness import CATALOGUE, complete_plan

USER_ID = "user-1"


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the plan's prescriptions without a database behind them."""

    async def fetch_exercises_by_id(exercise_ids: list[str]) -> dict:
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    monkeypatch.setattr(
        plan_presentation, "fetch_exercises_by_id", fetch_exercises_by_id
    )


def _runtime(context: object) -> ToolRuntime:
    """The runtime the agent builds around a tool call, carrying the coach's context."""
    return ToolRuntime(
        state=None,
        config={},
        stream_writer=None,
        tool_call_id="call_1",
        store=None,
        context=context,
    )


async def _invoke(context: object) -> ToolMessage:
    """Call the tool the way the agent's tool node does, so the artifact comes back too."""
    return await get_plan.ainvoke(
        {
            "type": "tool_call",
            "name": get_plan.name,
            "args": {"runtime": _runtime(context)},
            "id": "call_1",
        }
    )


# --- What the coach gets back -------------------------------------------------------------


async def test_a_stored_plan_comes_back_named_rather_than_by_id(
    store, catalogue
) -> None:
    """Ids are what the plan prescribes by and what an answer must never repeat back."""
    await save_plan(USER_ID, complete_plan().model_dump(mode="json"))

    result = await _invoke(CoachContext(user_id=USER_ID))

    assert "Barbell bench press" in result.content


async def test_the_stored_plan_is_handed_back_whole_as_the_artifact(
    store, catalogue
) -> None:
    """The rendering is what the model reads; the record is what the caller keeps."""
    plan = complete_plan().model_dump(mode="json")
    await save_plan(USER_ID, plan)

    result = await _invoke(CoachContext(user_id=USER_ID))

    assert result.artifact == {"plan": plan}


async def test_a_user_with_no_plan_is_told_so_in_words(store) -> None:
    """An empty result reads to the model as a lookup worth retrying; the sentence does not."""
    result = await _invoke(CoachContext(user_id=USER_ID))

    assert result.content == NO_PLAN_RECORDED
    assert result.artifact == {"plan": None}


async def test_a_plan_the_renderer_cannot_read_is_still_returned(store) -> None:
    """An older schema is still the user's plan: it degrades to the record, not to nothing."""
    stored = {"template_id": "t-1", "days": ["monday"]}
    await save_plan(USER_ID, stored)

    result = await _invoke(CoachContext(user_id=USER_ID))

    assert json.loads(result.content) == stored
    assert result.artifact == {"plan": stored}


# --- Whose plan it is ---------------------------------------------------------------------


async def test_the_user_comes_from_the_runtime(store, catalogue) -> None:
    """The tool takes no arguments at all, so the model cannot name a different user."""
    await save_plan("user-2", complete_plan().model_dump(mode="json"))

    result = await _invoke(CoachContext(user_id=USER_ID))

    assert result.content == NO_PLAN_RECORDED


async def test_a_runtime_without_a_user_reads_no_plan(store) -> None:
    """Reaching the store with an empty id raises; the tool must answer before it does."""
    assert (await _invoke(CoachContext(user_id=""))).content == NO_PLAN_RECORDED
    assert (await _invoke(None)).content == NO_PLAN_RECORDED
