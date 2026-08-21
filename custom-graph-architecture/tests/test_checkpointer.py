"""Checkpointer integration tests.

The interrupt/resume roundtrip is asserted across two separately compiled graphs, so state
that only survived in process memory would fail the test. That is the mechanism both
``wait_for_user`` and ``hitl_review`` rely on.
"""

from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from app.core.langgraph.runtime.checkpointer import CheckpointerResource

THREAD_ID = "test-checkpointer-thread"


class _State(TypedDict):
    question: str
    answer: str


async def _ask(state: _State) -> _State:
    """Suspend the graph and return whatever the caller resumes with."""
    return {"answer": interrupt({"question": state["question"]})}


def _build(saver: Any):
    builder = StateGraph(_State)
    builder.add_node("ask", _ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    return builder.compile(checkpointer=saver, name="checkpointer_test")


@pytest.fixture
async def resource(require_postgres: None):
    """Provide a checkpointer resource and close its pool afterwards."""
    resource = CheckpointerResource()
    yield resource
    await resource.close()


async def test_get_opens_the_pool_once(resource: CheckpointerResource) -> None:
    """Repeat calls reuse the same saver rather than reopening the pool per request."""
    first = await resource.get()
    second = await resource.get()

    assert first is second


async def test_setup_creates_the_checkpoint_tables(resource: CheckpointerResource) -> None:
    """``setup()`` migrates the checkpointer's own tables into the database."""
    saver = await resource.get()

    async with saver.conn.connection() as conn:
        cursor = await conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename LIKE 'checkpoint%'"
        )
        tables = {row["tablename"] for row in await cursor.fetchall()}

    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"} <= tables


async def test_state_survives_interrupt_and_resumes_from_postgres(
    resource: CheckpointerResource,
) -> None:
    """A graph suspended by ``interrupt()`` resumes in a later, freshly compiled graph."""
    saver = await resource.get()
    await saver.adelete_thread(THREAD_ID)
    config = {"configurable": {"thread_id": THREAD_ID}}

    suspended = await _build(saver).ainvoke({"question": "training days per week?"}, config)
    assert suspended["__interrupt__"][0].value == {"question": "training days per week?"}
    assert (await _build(saver).aget_state(config)).next == ("ask",)

    resumed = await _build(saver).ainvoke(Command(resume="4"), config)
    assert resumed["answer"] == "4"
    assert (await _build(saver).aget_state(config)).next == ()

    await saver.adelete_thread(THREAD_ID)
    assert (await _build(saver).aget_state(config)).values == {}
