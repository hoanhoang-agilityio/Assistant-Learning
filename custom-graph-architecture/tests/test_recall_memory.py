"""Tests for the ``recall_memory`` tool: what reaches the coach, and whose memory it is."""

import pytest
from langchain.tools import ToolRuntime

import src.services.memory as memory_service
from src.core.langgraph.runtime import MemoryScope
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.core.langgraph.tools.recall_memory import NOTHING_RECORDED, recall_memory
from src.schemas import CoachContext, QaContext
from src.services.memory import save
from src.services.profile import save_profile

USER_ID = "user-1"

FOUR_DAY_SPLIT = {"days_per_week": 4}
SKIPS_LONG_SESSIONS = {"pattern": "skips sessions over 60 minutes"}


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


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


async def _invoke(context: object) -> dict:
    """Call the tool the way the agent's tool node does."""
    return await recall_memory.ainvoke({"runtime": _runtime(context)})


# --- What the coach gets back -------------------------------------------------------------


async def test_both_scopes_reach_the_coach(store) -> None:
    """A stated preference and an observed pattern are different evidence, kept apart."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await save(USER_ID, MemoryScope.KNOWLEDGE, "adherence", SKIPS_LONG_SESSIONS)

    assert await _invoke(CoachContext(user_id=USER_ID)) == {
        "preferences": {"schedule": FOUR_DAY_SPLIT},
        "knowledge": {"adherence": SKIPS_LONG_SESSIONS},
    }


async def test_a_first_time_user_is_told_to_plan_from_the_profile(store) -> None:
    """An empty dict reads to the model as a lookup worth retrying; the sentence does not."""
    assert await _invoke(CoachContext(user_id=USER_ID)) == {"error": NOTHING_RECORDED}


async def test_one_scope_alone_is_still_returned(store) -> None:
    """A user with patterns but no stated preferences must not fall to the empty case."""
    await save(USER_ID, MemoryScope.KNOWLEDGE, "adherence", SKIPS_LONG_SESSIONS)

    assert await _invoke(CoachContext(user_id=USER_ID)) == {
        "preferences": {},
        "knowledge": {"adherence": SKIPS_LONG_SESSIONS},
    }


async def test_the_profile_is_not_returned_as_memory(store) -> None:
    """Facts are handed to the coach in its context block; repeating them costs tokens."""
    await save_profile(USER_ID, {"age": 34})

    assert await _invoke(CoachContext(user_id=USER_ID)) == {"error": NOTHING_RECORDED}


# --- Whose memory it is -------------------------------------------------------------------


async def test_the_user_comes_from_the_runtime(store) -> None:
    """The tool takes no arguments at all, so the model cannot name a different user."""
    await save("user-2", MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    assert await _invoke(CoachContext(user_id=USER_ID)) == {"error": NOTHING_RECORDED}


async def test_a_runtime_without_a_user_recalls_nothing(store) -> None:
    """Reaching the store with an empty id raises; the tool must answer before it does."""
    assert await _invoke(CoachContext(user_id="")) == {"error": NOTHING_RECORDED}
    assert await _invoke(None) == {"error": NOTHING_RECORDED}


async def test_the_qa_context_carries_a_user_too(store) -> None:
    """The context helper is shared, so the tool must not assume one of the two shapes."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    assert await _invoke(QaContext(user_id=USER_ID)) == {
        "preferences": {"schedule": FOUR_DAY_SPLIT},
        "knowledge": {},
    }
