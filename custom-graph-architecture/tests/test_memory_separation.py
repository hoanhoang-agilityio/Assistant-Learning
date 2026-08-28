"""Integration tests for the boundary between the two memories.

The checkpointer is keyed by ``thread_id`` and the store is keyed by ``user_id``, and the
whole design rests on those being different keys: a user who starts a new conversation must
lose the previous run's working state and keep everything the store recorded about them.
Nothing here mocks the seam — each test drives a real graph against a real backend.

Parametrised over every registered backend, so the same claims are asserted in-process and
against Postgres. The Postgres runs are marked ``integration`` and skip without a database.
"""

from typing import Any

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

import src.services.memory as memory_service
from src.configs.config import PersistenceBackend
from src.runtime import MemoryScope, namespace_for
from src.runtime.backends import RUNTIMES, build_runtime
from src.runtime.base import GraphRuntime
from src.services.memory import delete, load_user_memory, recall, save
from src.services.profile import load_profile, save_profile

USER_ID = "separation-user"
OTHER_USER_ID = "separation-user-2"
THREAD_A = "separation-thread-a"
THREAD_B = "separation-thread-b"

PROFILE = {"age": 34, "goal": "FAT_LOSS"}
FOUR_DAY_SPLIT = {"days_per_week": 4}

_NEEDS_SERVICE = {PersistenceBackend.POSTGRES}


class _State(TypedDict):
    """A run's working state: what the checkpointer holds and the store must not."""

    user_id: str
    draft: str
    recalled: dict


async def _recall(state: _State) -> _State:
    """Read long-term memory into the run, the way ``load_user_context`` does."""
    memory = await load_user_memory(state["user_id"])
    return {"recalled": memory.preferences}


async def _ask(state: _State) -> _State:
    """Suspend the run, the way ``wait_for_user`` and ``hitl_review`` do."""
    return {"draft": interrupt({"prompt": "how many days?"})}


def _build(saver: BaseCheckpointSaver) -> Any:
    """Compile the two-node graph fresh, as a new request would."""
    builder = StateGraph(_State)
    builder.add_node("recall", _recall)
    builder.add_node("ask", _ask)
    builder.add_edge(START, "recall")
    builder.add_edge("recall", "ask")
    builder.add_edge("ask", END)
    return builder.compile(checkpointer=saver, name="separation_test")


def _config(thread_id: str) -> dict:
    """The config that scopes a run to one thread."""
    return {"configurable": {"thread_id": thread_id}}


def _backend_params() -> list[pytest.param]:
    """One fixture param per registered backend, marked if it needs a real service."""
    return [
        pytest.param(
            backend,
            id=backend.value,
            marks=[pytest.mark.integration] if backend in _NEEDS_SERVICE else [],
        )
        for backend in RUNTIMES
    ]


@pytest.fixture(params=_backend_params())
async def runtime(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at one backend and clear what the test leaves behind.

    Postgres is shared and persistent by definition, so the teardown is what keeps a run
    from seeing the previous run's rows.
    """
    backend: PersistenceBackend = request.param
    if backend in _NEEDS_SERVICE:
        request.getfixturevalue("require_postgres")

    runtime = build_runtime(backend)
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    await _clear(runtime)

    yield runtime

    await _clear(runtime)
    await runtime.close()


async def _clear(runtime: GraphRuntime) -> None:
    """Drop every thread and every namespace these tests write to."""
    checkpointer = await runtime.checkpointer()
    for thread_id in (THREAD_A, THREAD_B):
        await checkpointer.adelete_thread(thread_id)

    store = await runtime.store()
    for user_id in (USER_ID, OTHER_USER_ID):
        for scope in MemoryScope:
            namespace = namespace_for(user_id, scope)
            for item in await store.asearch(namespace, limit=100):
                await store.adelete(namespace, item.key)


# --- A new conversation --------------------------------------------------------------------


async def test_a_new_thread_does_not_inherit_the_previous_runs_state(
    runtime: GraphRuntime,
) -> None:
    """Working state is the run's, not the user's — a new conversation starts empty."""
    saver = await runtime.checkpointer()
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))
    await _build(saver).ainvoke(Command(resume="4"), _config(THREAD_A))

    assert (await _build(saver).aget_state(_config(THREAD_A))).values["draft"] == "4"
    assert "draft" not in (await _build(saver).aget_state(_config(THREAD_B))).values


async def test_a_new_thread_still_sees_what_the_store_recorded(
    runtime: GraphRuntime,
) -> None:
    """The point of the split: the conversation resets and the user does not."""
    saver = await runtime.checkpointer()
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await save_profile(USER_ID, PROFILE)

    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_B))

    state = await _build(saver).aget_state(_config(THREAD_B))
    assert state.values["recalled"] == {"schedule": FOUR_DAY_SPLIT}
    assert await load_profile(USER_ID) == PROFILE


async def test_two_threads_read_one_users_memory(runtime: GraphRuntime) -> None:
    """Two conversations at once are two checkpoints over a single long-term memory."""
    saver = await runtime.checkpointer()
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_B))

    for thread_id in (THREAD_A, THREAD_B):
        state = await _build(saver).aget_state(_config(thread_id))
        assert state.values["recalled"] == {"schedule": FOUR_DAY_SPLIT}


async def test_a_suspended_run_keeps_its_own_state_while_another_thread_runs(
    runtime: GraphRuntime,
) -> None:
    """A user parked at an ``interrupt()`` must not be disturbed by their other tab."""
    saver = await runtime.checkpointer()
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))

    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_B))
    await _build(saver).ainvoke(Command(resume="6"), _config(THREAD_B))

    assert (await _build(saver).aget_state(_config(THREAD_A))).next == ("ask",)
    resumed = await _build(saver).ainvoke(Command(resume="4"), _config(THREAD_A))
    assert resumed["draft"] == "4"


# --- Neither memory leaks into the other -----------------------------------------------------


async def test_run_state_is_never_written_to_long_term_memory(
    runtime: GraphRuntime,
) -> None:
    """A draft the user has not approved is checkpoint data; storing it would outlive them."""
    saver = await runtime.checkpointer()
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))
    await _build(saver).ainvoke(Command(resume="4"), _config(THREAD_A))

    assert (await load_user_memory(USER_ID)).is_empty
    assert await load_profile(USER_ID) is None


async def test_a_long_term_write_does_not_touch_the_running_thread(
    runtime: GraphRuntime,
) -> None:
    """The store is read into state at ``recall``; a later write must not rewrite the run."""
    saver = await runtime.checkpointer()
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))

    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    state = await _build(saver).aget_state(_config(THREAD_A))
    assert state.values["recalled"] == {}
    assert state.next == ("ask",)


async def test_one_users_memory_is_not_reachable_from_anothers_thread(
    runtime: GraphRuntime,
) -> None:
    """The store's key is the user, so a shared thread id would still not share memory."""
    saver = await runtime.checkpointer()
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    await _build(saver).ainvoke({"user_id": OTHER_USER_ID}, _config(THREAD_A))

    assert (await _build(saver).aget_state(_config(THREAD_A))).values["recalled"] == {}


# --- Deleting one does not delete the other ---------------------------------------------------


async def test_deleting_a_thread_leaves_the_user_intact(runtime: GraphRuntime) -> None:
    """Clearing a conversation is what the UI offers; it must not clear the profile."""
    saver = await runtime.checkpointer()
    await save_profile(USER_ID, PROFILE)
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))

    await saver.adelete_thread(THREAD_A)

    assert (await _build(saver).aget_state(_config(THREAD_A))).values == {}
    assert await load_profile(USER_ID) == PROFILE
    assert await recall(USER_ID, MemoryScope.PREFERENCES, "schedule") == FOUR_DAY_SPLIT


async def test_forgetting_a_memory_leaves_the_thread_intact(
    runtime: GraphRuntime,
) -> None:
    """The reverse direction: dropping a stored preference must not lose a suspended run."""
    saver = await runtime.checkpointer()
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await _build(saver).ainvoke({"user_id": USER_ID}, _config(THREAD_A))

    await delete(USER_ID, MemoryScope.PREFERENCES, "schedule")

    assert await recall(USER_ID, MemoryScope.PREFERENCES, "schedule") is None
    assert (await _build(saver).aget_state(_config(THREAD_A))).next == ("ask",)
    assert (await _build(saver).ainvoke(Command(resume="4"), _config(THREAD_A)))[
        "draft"
    ] == "4"


# --- The two live in different tables ---------------------------------------------------------


@pytest.mark.integration
async def test_the_two_memories_are_stored_apart(require_postgres: None) -> None:
    """Short-term rows are the checkpointer's; long-term rows are the store's."""
    runtime = build_runtime(PersistenceBackend.POSTGRES)
    try:
        checkpointer = await runtime.checkpointer()
        store = await runtime.store()

        async with checkpointer.conn.connection() as conn:
            cursor = await conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            tables = {row["tablename"] for row in await cursor.fetchall()}
    finally:
        await runtime.close()

    assert {"checkpoints", "store"} <= tables
    assert checkpointer.conn is store.conn
