"""Tests for long-term memory and the cache in front of it.

Memory is the one subsystem here that is *optional to the answer*. Everything it
does must therefore fail soft: an unavailable pgvector, a dead Valkey, a slow
mem0 — none of them may cost the user their reply. The tests below are mostly
about that, plus the one thing that must never fail soft: keeping one user's
memories away from another's.
"""

import asyncio

import pytest

from app.core.cache import CacheService
from app.services.memory import NO_MEMORY, MemoryService, _cache_key


class _FakeMem0:
    """Stand-in for mem0's AsyncMemory.

    The signatures mirror mem0 2.x deliberately, including the keyword-only
    markers. mem0 2.x scopes a search through ``filters`` and *rejects* a
    top-level ``user_id``; a fake that accepted anything would let this suite
    stay green while the real client raised on every call.
    """

    def __init__(self, results=None, fail=False) -> None:
        self.results = results if results is not None else []
        self.fail = fail
        self.searches: list[tuple[str, str]] = []
        self.adds: list[tuple[str, list]] = []

    async def search(self, query, *, filters=None, top_k=20, **_kwargs):
        self.searches.append(((filters or {}).get("user_id"), query))
        if self.fail:
            raise RuntimeError("pgvector unavailable")
        return {"results": self.results}

    async def add(self, messages, *, user_id=None, metadata=None, **_kwargs):
        if self.fail:
            raise RuntimeError("pgvector unavailable")
        self.adds.append((user_id, messages))


@pytest.fixture
def cache() -> CacheService:
    """An in-process cache, the default backend when VALKEY_HOST is unset."""
    return CacheService()


@pytest.fixture
def memory(monkeypatch, cache) -> MemoryService:
    """A memory service wired to the in-process cache."""
    monkeypatch.setattr("app.services.memory.cache_service", cache)
    return MemoryService()


def _wire(memory: MemoryService, client: _FakeMem0) -> _FakeMem0:
    """Attach a fake mem0 client, skipping real initialisation."""
    memory._memory = client
    memory._unavailable = False
    return client


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


async def test_an_anonymous_user_gets_nothing_and_stores_nothing(memory):
    """The worst available failure: one stranger's details reaching another.

    Anonymous turns have no owner, so pooling them under a shared key would do
    exactly that. They get nothing back and write nothing.
    """
    client = _wire(memory, _FakeMem0(results=[{"memory": "trains at 6am"}]))

    assert await memory.search(None, "when do I train?") == NO_MEMORY
    await memory.add(None, [{"role": "user", "content": "I train at 6am"}])

    assert client.searches == []
    assert client.adds == []


async def test_searches_are_scoped_to_the_user(memory):
    """user_id is the isolation boundary, and it must reach mem0 as a filter.

    Passing it any other way is not a subtle bug: mem0 2.x raises on a
    top-level ``user_id``, so the alternative to a correct filter is a search
    that never runs — and, because search fails soft, one that fails silently.
    """
    client = _wire(memory, _FakeMem0())
    await memory.search("42", "anything")
    assert client.searches == [("42", "anything")]


async def test_the_call_matches_the_installed_mem0_signature(memory):
    """Bind the real signature against the arguments the service sends.

    Catches a mem0 upgrade that renames or reorders these parameters, which
    would otherwise show up only as memory quietly never working.
    """
    import inspect

    from mem0 import AsyncMemory

    inspect.signature(AsyncMemory.search).bind(None, query="q", filters={"user_id": "1"}, top_k=5)
    inspect.signature(AsyncMemory.add).bind(
        None, [{"role": "user", "content": "x"}], user_id="1", metadata={}
    )


def test_cache_keys_do_not_collide_across_users():
    """Two users asking the same question must not share a cache entry."""
    assert _cache_key("1", "how much protein?") != _cache_key("2", "how much protein?")


def test_cache_keys_do_not_leak_the_query():
    """Queries are user text and must not end up in key names or logs."""
    key = _cache_key("1", "my doctor said my knee is arthritic")
    assert "knee" not in key and "doctor" not in key
    assert key.startswith("memory:")


# ---------------------------------------------------------------------------
# Failing soft
# ---------------------------------------------------------------------------


async def test_a_search_failure_returns_empty_rather_than_raising(memory):
    """A pgvector outage costs personalisation, never the answer."""
    _wire(memory, _FakeMem0(fail=True))
    assert await memory.search("1", "anything") == NO_MEMORY


async def test_a_write_failure_is_swallowed(memory):
    """Losing a memory write is invisible this turn and recoverable next turn."""
    _wire(memory, _FakeMem0(fail=True))
    await memory.add("1", [{"role": "user", "content": "hello"}])


async def test_an_unavailable_service_short_circuits(memory):
    """When mem0 could not start, callers skip the work rather than retrying."""
    memory._unavailable = True
    assert memory.enabled is False
    assert await memory.search("1", "anything") == NO_MEMORY


async def test_a_dead_cache_backend_reads_as_a_miss(cache):
    """A Valkey outage must degrade to a cache miss, not to a failed request.

    Raising here would turn a restart of an optional service into failed chat
    turns — strictly worse than the uncached latency the cache exists to avoid.
    """

    class _DeadClient:
        async def get(self, _key):
            raise ConnectionError("valkey down")

        async def set(self, *_args, **_kwargs):
            raise ConnectionError("valkey down")

    cache._client = _DeadClient()

    assert await cache.get("k") is None
    await cache.set("k", "v")


async def test_memory_still_answers_when_the_cache_is_dead(memory, cache):
    """With no usable cache, search falls through to the store and succeeds."""

    class _DeadClient:
        async def get(self, _key):
            raise ConnectionError("valkey down")

        async def set(self, *_args, **_kwargs):
            raise ConnectionError("valkey down")

    cache._client = _DeadClient()
    _wire(memory, _FakeMem0(results=[{"memory": "trains at 6am"}]))

    assert await memory.search("1", "when?") == "- trains at 6am"


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


async def test_a_repeated_search_is_served_from_cache(memory):
    """The cache exists to stop paying pgvector twice for the same question."""
    client = _wire(memory, _FakeMem0(results=[{"memory": "trains at 6am"}]))

    first = await memory.search("1", "when do I train?")
    second = await memory.search("1", "when do I train?")

    assert first == second == "- trains at 6am"
    assert len(client.searches) == 1, "the second search hit the store"


async def test_an_empty_result_is_not_cached(memory):
    """Caching "no memories" would pin that answer across the turn that creates some."""
    client = _wire(memory, _FakeMem0(results=[]))

    await memory.search("1", "anything")
    await memory.search("1", "anything")

    assert len(client.searches) == 2, "an empty result was cached"


async def test_results_are_rendered_as_a_list(memory):
    """The prompt receives readable lines, not raw mem0 payloads."""
    _wire(memory, _FakeMem0(results=[{"memory": "travels often"}, {"memory": "hates burpees"}]))
    assert await memory.search("1", "x") == "- travels often\n- hates burpees"


# ---------------------------------------------------------------------------
# Background writes
# ---------------------------------------------------------------------------


async def test_a_background_write_is_not_awaited_but_still_happens(memory):
    """The user waits for their plan, not for the assistant's notes about them."""
    client = _wire(memory, _FakeMem0())

    memory.add_in_background("1", [{"role": "user", "content": "I travel a lot"}])
    assert client.adds == [], "the write blocked the caller"

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(client.adds) == 1


async def test_background_writes_keep_a_strong_reference(memory):
    """A bare create_task may be collected mid-flight, losing the write silently."""
    from app.services.memory import _BACKGROUND_TASKS

    _wire(memory, _FakeMem0())
    memory.add_in_background("1", [{"role": "user", "content": "x"}])
    assert _BACKGROUND_TASKS, "no reference was retained"

    await asyncio.sleep(0)
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Cache service
# ---------------------------------------------------------------------------


async def test_cache_round_trips(cache):
    """The in-process backend is a real cache, not a no-op."""
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


async def test_a_missing_key_is_none(cache):
    """A miss is None, so callers can tell it apart from a cached empty string."""
    assert await cache.get("nope") is None


async def test_the_default_backend_needs_no_service(cache):
    """Local development must not require Valkey to be running."""
    await cache.initialize()
    assert cache.backend == "memory"


async def test_close_is_safe_without_a_connection(cache):
    """Shutdown must not fail when the cache never connected."""
    await cache.initialize()
    await cache.close()


# ---------------------------------------------------------------------------
# One search per turn
# ---------------------------------------------------------------------------


def test_no_agent_searches_memory_for_itself():
    """Skill §4: memory is searched once at the root and passed down in state.

    An agent calling `memory_service.search` would turn one pgvector query per
    request into one per agent, and let two agents reason over different
    retrievals of the same fact.
    """
    from pathlib import Path

    agents_dir = Path(__file__).resolve().parent.parent / "app" / "core" / "langgraph" / "agents"
    offenders = [
        path.relative_to(agents_dir).as_posix()
        for path in agents_dir.rglob("*.py")
        if "memory_service" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"agents querying memory directly: {offenders}"


def test_the_qa_agent_reads_memory_from_state():
    """The one agent that personalises must receive memory, not fetch it."""
    from app.core.langgraph.agents.qa import QAState

    assert "long_term_memory" in QAState.__annotations__


# ---------------------------------------------------------------------------
# Reading model output
# ---------------------------------------------------------------------------


def test_reasoning_model_content_blocks_are_read_as_text():
    """A reasoning model returns content *blocks*, not a string.

    This is the failure a real API call exposed and 196 stubbed tests did not:
    every stub returned ``AIMessage(content="...")`` with a plain string, while
    the live model returned ``[{'type': 'reasoning'}, {'type': 'text'}]``. The
    old `content if isinstance(content, str) else ""` yielded an empty answer —
    nothing raised, the turn "succeeded", and the user got nothing.
    """
    from langchain_core.messages import AIMessage

    from app.core.langgraph.utils import message_text

    blocks = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "thinking about it"},
            {"type": "text", "text": "Here is your plan."},
        ]
    )
    assert message_text(blocks) == "Here is your plan."
    assert message_text(AIMessage(content="plain string")) == "plain string"
    assert message_text(AIMessage(content=[])) == ""


def test_no_node_reads_content_directly():
    """`message_text` is the only correct way to read a model response.

    A direct `.content` read reintroduces the empty-answer bug for reasoning
    models, and it does so silently.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "app"
    offenders = [
        f"{path.relative_to(root)}:{n}"
        for path in root.rglob("*.py")
        if path.name != "utils.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "isinstance(" in line and ".content, str)" in line
    ]
    assert offenders == [], f"reads .content directly instead of message_text: {offenders}"
