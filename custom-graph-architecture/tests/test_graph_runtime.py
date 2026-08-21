"""Contract tests for the persistence seam.

The behavioural tests are parametrised over every registered backend, so a new backend
inherits the whole suite by adding one line to ``RUNTIMES``. Anything Postgres-only —
its pool, its migrated tables, the pgvector extension — lives in the last section and
skips when no database is reachable.
"""

from typing import Any

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from src.core.configs.config import PersistenceBackend, Settings
from src.core.langgraph.runtime import graph_runtime, namespace_for
from src.core.langgraph.runtime.backends import RUNTIMES, build_runtime
from src.core.langgraph.runtime.backends.postgres import PostgresRuntime
from src.core.langgraph.runtime.base import GraphRuntime
from src.core.langgraph.runtime.namespaces import MemoryScope

THREAD_ID = "test-runtime-thread"


class _State(TypedDict):
    question: str
    answer: str


async def _ask(state: _State) -> _State:
    """Suspend the graph and return whatever the caller resumes with."""
    return {"answer": interrupt({"question": state["question"]})}


def _build(saver: BaseCheckpointSaver) -> Any:
    builder = StateGraph(_State)
    builder.add_node("ask", _ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    return builder.compile(checkpointer=saver, name="runtime_test")


# Backends that need something running outside the test process.
_NEEDS_SERVICE = {PersistenceBackend.POSTGRES}


def _backend_params() -> list[pytest.param]:
    """One fixture param per registered backend, marked if it needs a real service.

    Marks belong on the param rather than inside the fixture: ``-m`` filtering happens at
    collection, so a marker added at fixture time is never seen.
    """
    return [
        pytest.param(
            backend,
            id=backend.value,
            marks=[pytest.mark.integration] if backend in _NEEDS_SERVICE else [],
        )
        for backend in RUNTIMES
    ]


@pytest.fixture(params=_backend_params())
async def runtime(request: pytest.FixtureRequest):
    """Provide each registered backend in turn, closing it afterwards.

    Skips a backend whose dependency is unavailable rather than failing, so the suite still
    runs without ``docker compose up db``.
    """
    backend: PersistenceBackend = request.param
    if backend in _NEEDS_SERVICE:
        request.getfixturevalue("require_postgres")

    runtime = build_runtime(backend)
    yield runtime
    await runtime.close()


# --- Seam ------------------------------------------------------------------------------


def test_registry_covers_every_declared_backend() -> None:
    """A value on the enum with no implementation would fail only at startup."""
    assert set(RUNTIMES) == set(PersistenceBackend)


def test_unregistered_backend_is_rejected() -> None:
    """``build_runtime`` fails loudly rather than returning None."""
    with pytest.raises(ValueError, match="no runtime registered"):
        build_runtime("cassandra")  # type: ignore[arg-type]


def test_exported_runtime_is_typed_to_the_abstraction() -> None:
    """Callers import the seam, so nothing can depend on a backend-only method."""
    assert isinstance(graph_runtime, GraphRuntime)


def test_default_backend_is_durable() -> None:
    """An interrupt gate can only be resumed from a backend that survives a restart.

    Asserts the declared default rather than the resolved value, so the test still means
    something when a run overrides ``PERSISTENCE_BACKEND`` in the environment.
    """
    assert (
        Settings.model_fields["PERSISTENCE_BACKEND"].default
        is PersistenceBackend.POSTGRES
    )


# --- Behaviour, on every backend -------------------------------------------------------


async def test_backends_satisfy_the_abcs(runtime: GraphRuntime) -> None:
    """Every backend hands back the framework's interfaces, not its own types."""
    assert isinstance(await runtime.checkpointer(), BaseCheckpointSaver)
    assert isinstance(await runtime.store(), BaseStore)


async def test_backends_are_cached(runtime: GraphRuntime) -> None:
    """Repeat calls reuse one instance rather than re-running setup per request."""
    assert await runtime.checkpointer() is await runtime.checkpointer()
    assert await runtime.store() is await runtime.store()


async def test_state_survives_interrupt_and_resumes(runtime: GraphRuntime) -> None:
    """A graph suspended by ``interrupt()`` resumes in a later, freshly compiled graph."""
    saver = await runtime.checkpointer()
    config = {"configurable": {"thread_id": THREAD_ID}}

    suspended = await _build(saver).ainvoke(
        {"question": "training days per week?"}, config
    )
    assert suspended["__interrupt__"][0].value == {
        "question": "training days per week?"
    }
    assert (await _build(saver).aget_state(config)).next == ("ask",)

    resumed = await _build(saver).ainvoke(Command(resume="4"), config)
    assert resumed["answer"] == "4"
    assert (await _build(saver).aget_state(config)).next == ()


async def test_long_term_memory_is_scoped_per_user(runtime: GraphRuntime) -> None:
    """One user's stored facts are not visible in another user's namespace."""
    store = await runtime.store()
    alice = namespace_for("alice", MemoryScope.FACTS)
    bob = namespace_for("bob", MemoryScope.FACTS)

    await store.aput(alice, "weight", {"current_weight_kg": 72.0})
    try:
        assert (await store.aget(alice, "weight")).value == {"current_weight_kg": 72.0}
        assert await store.aget(bob, "weight") is None
    finally:
        await store.adelete(alice, "weight")


async def test_memory_scopes_do_not_collide(runtime: GraphRuntime) -> None:
    """The same key in two scopes for one user addresses two different entries."""
    store = await runtime.store()
    facts = namespace_for("carol", MemoryScope.FACTS)
    preferences = namespace_for("carol", MemoryScope.PREFERENCES)

    await store.aput(facts, "schedule", {"source": "profile"})
    await store.aput(preferences, "schedule", {"source": "stated"})
    try:
        assert (await store.aget(facts, "schedule")).value == {"source": "profile"}
        assert (await store.aget(preferences, "schedule")).value == {"source": "stated"}
    finally:
        await store.adelete(facts, "schedule")
        await store.adelete(preferences, "schedule")


# --- Postgres specifics ----------------------------------------------------------------


@pytest.fixture
async def postgres_runtime(require_postgres: None):
    """Provide a Postgres runtime and close its pool afterwards."""
    runtime = PostgresRuntime()
    yield runtime
    await runtime.close()


@pytest.mark.integration
async def test_checkpointer_and_store_share_one_pool(
    postgres_runtime: PostgresRuntime,
) -> None:
    """Both Postgres backends borrow from the same connection pool."""
    checkpointer = await postgres_runtime.checkpointer()
    store = await postgres_runtime.store()

    assert checkpointer.conn is store.conn


@pytest.mark.integration
async def test_setup_creates_checkpointer_and_store_tables(
    postgres_runtime: PostgresRuntime,
) -> None:
    """Each backend migrates its own tables; Alembic owns neither."""
    checkpointer = await postgres_runtime.checkpointer()
    await postgres_runtime.store()

    async with checkpointer.conn.connection() as conn:
        cursor = await conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {row["tablename"] for row in await cursor.fetchall()}

    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"} <= tables
    assert "store" in tables


@pytest.mark.integration
async def test_pgvector_extension_is_installed(
    postgres_runtime: PostgresRuntime,
) -> None:
    """The knowledge base and any future vector index need the extension present."""
    checkpointer = await postgres_runtime.checkpointer()

    async with checkpointer.conn.connection() as conn:
        cursor = await conn.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        row = await cursor.fetchone()

    assert row is not None, "pgvector missing — run `uv run alembic upgrade head`"
