"""Long-term memory over mem0 + pgvector.

Facts about the user that outlive a session and are not structured enough for
the profile table: that they travel most weeks, that their gym is busy at 6pm,
that they disliked a programme they tried last year. The profile holds what the
pipeline computes with; this holds what makes the assistant sound like it
remembers them.

Four rules, each load-bearing:

**``user_id`` is the isolation boundary.** An anonymous turn gets ``""`` back and
writes nothing. Pooling anonymous users under a shared key would surface one
stranger's details to another, which is the worst failure available here.

**Memory never breaks chat.** Every search catches, logs and returns ``""``. A
pgvector timeout must cost personalisation, not the answer.

**Writes happen in the background.** ``add()`` runs an LLM extraction pass; the
user waits for their plan, not for the assistant's notes about them.

**One search per turn, at the root.** With five agents, a per-agent search would
multiply the cost and let different agents reason over different retrievals of
the same fact.
"""

import asyncio
import hashlib
import os
from typing import Any

from app.core.cache import cache_service
from app.core.configs.config import settings
from app.core.logging import logger

# What the caller substitutes when nothing is retrieved, so the prompt reads the
# same whether memory was empty, disabled or unavailable.
NO_MEMORY = ""

_MAX_RESULTS = 5
_CACHE_PREFIX = "memory"

# Model families that reject `temperature` and `top_p` outright.
_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    """Report whether mem0 must omit the sampling parameters for this model.

    mem0 makes this call itself, from a hardcoded name set
    (``LLMBase._is_reasoning_model``) that matches ``gpt-5`` exactly but not
    ``gpt-5-nano`` or ``gpt-5-mini``. Misclassified, it sends ``temperature``
    and ``top_p``, the API rejects both with a 400, and every extraction fails
    — silently, because ``add()`` logs and swallows. The result is a memory
    store that initialises cleanly, answers searches, and is permanently empty.

    Deciding it here rather than letting mem0 guess also means changing
    ``LONG_TERM_MEMORY_MODEL`` cannot quietly turn memory off again.

    Args:
        model: The configured extraction model.

    Returns:
        ``True`` when the model only accepts the default sampling parameters.
    """
    return model.lower().startswith(_REASONING_MODEL_PREFIXES)


def _cache_key(user_id: str, query: str) -> str:
    """Build the cache key for one search.

    Hashed rather than raw: the query is user text and would otherwise put
    arbitrary content into key names and logs.

    Args:
        user_id: Owner of the memories.
        query: The search text.

    Returns:
        A short, stable key.
    """
    digest = hashlib.sha256(f"{user_id}:{query}".encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{digest}"


class MemoryService:
    """Per-user long-term memory, with a cache in front of search."""

    def __init__(self) -> None:
        """Prepare a lazily-created mem0 client."""
        self._memory: Any = None
        self._unavailable = False

    @property
    def enabled(self) -> bool:
        """Whether memory is usable at all.

        Returns:
            ``False`` when mem0 could not be initialised, so callers can skip
            the work entirely rather than failing per request.
        """
        return not self._unavailable

    def _config(self) -> dict[str, Any]:
        """Build the mem0 configuration.

        pgvector is used as the store so memories live in the same database as
        everything else — one backup, one connection story. The collection is
        owned by mem0 and is excluded from Alembic autogenerate
        (``alembic/env.py::EXCLUDE_TABLES``); without that exclusion the next
        migration would propose dropping it.

        Returns:
            The mem0 config dict.
        """
        return {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_MODEL,
                    "api_key": settings.OPENAI_API_KEY,
                    "is_reasoning_model": _is_reasoning_model(settings.LONG_TERM_MEMORY_MODEL),
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_EMBEDDER_MODEL,
                    "api_key": settings.OPENAI_API_KEY,
                },
            },
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "user": settings.POSTGRES_USER,
                    "password": settings.POSTGRES_PASSWORD,
                    "host": settings.POSTGRES_HOST,
                    "port": settings.POSTGRES_PORT,
                    "dbname": settings.POSTGRES_DB,
                    "collection_name": settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                },
            },
        }

    async def _get_memory(self) -> Any:
        """Return the mem0 client, creating it on first use.

        Returns:
            The ``AsyncMemory`` instance, or ``None`` when it cannot be built.
        """
        if self._memory is not None or self._unavailable:
            return self._memory

        try:
            # Opt out of mem0's PostHog telemetry before importing it: the flag
            # is read at module import, and it defaults to on. Usage data about
            # a health-adjacent application should not leave the deployment
            # because a dependency ships analytics enabled.
            os.environ.setdefault("MEM0_TELEMETRY", "False")

            from mem0 import AsyncMemory

            # Not a coroutine in mem0 2.x despite the class name — awaiting it
            # raises "object AsyncMemory can't be used in 'await' expression".
            self._memory = AsyncMemory.from_config(self._config())
            logger.info(
                "memory_initialized",
                collection=settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                model=settings.LONG_TERM_MEMORY_MODEL,
            )
        except Exception as e:
            self._unavailable = True
            logger.warning("memory_unavailable", error=str(e))

        return self._memory

    async def initialize(self) -> None:
        """Pre-warm the client at startup.

        Called from the lifespan so the first real request does not pay mem0's
        cold init — which includes opening a pgvector connection and creating
        the collection if it does not exist.
        """
        if not settings.OPENAI_API_KEY:
            self._unavailable = True
            logger.info("memory_disabled_no_api_key")
            return
        await self._get_memory()

    async def search(self, user_id: str | None, query: str) -> str:
        """Retrieve what is remembered about this user, relevant to the query.

        Args:
            user_id: Owner of the memories. ``None`` for an anonymous session.
            query: The user's latest message.

        Returns:
            Retrieved facts as newline-separated text, or ``""`` when there is
            nothing, the user is anonymous, or anything at all went wrong.
        """
        if not user_id or not query or self._unavailable:
            return NO_MEMORY

        key = _cache_key(user_id, query)
        cached = await cache_service.get(key)
        if cached is not None:
            logger.debug("memory_cache_hit", user_id=user_id)
            return cached

        memory = await self._get_memory()
        if memory is None:
            return NO_MEMORY

        try:
            # mem0 2.x scopes a search through `filters`, and rejects a
            # top-level `user_id` outright. Getting this wrong is not a silent
            # bug — it raises — but the raise happens inside the try, so a
            # future API change costs personalisation rather than the turn.
            result = await memory.search(
                query=query, filters={"user_id": user_id}, top_k=_MAX_RESULTS
            )
        except Exception as e:
            logger.exception("memory_search_failed", user_id=user_id, error=str(e))
            return NO_MEMORY

        entries = result.get("results", []) if isinstance(result, dict) else (result or [])
        rendered = "\n".join(
            f"- {entry['memory']}"
            for entry in entries
            if isinstance(entry, dict) and entry.get("memory")
        )

        # Only successful, non-empty results are cached. Caching an empty result
        # would pin "this user has no memories" for the whole TTL, including
        # across the turn that just created some.
        if rendered:
            await cache_service.set(key, rendered)

        logger.info("memory_searched", user_id=user_id, results=len(entries))
        return rendered

    async def add(
        self, user_id: str | None, messages: list[dict[str, str]], metadata: dict | None = None
    ) -> None:
        """Record what this turn revealed about the user.

        Fire-and-forget: callers schedule this with ``asyncio.create_task`` after
        the response is produced, so the extraction pass mem0 runs never appears
        in the user's latency.

        Args:
            user_id: Owner of the memories. ``None`` skips the write entirely.
            messages: The turn, as ``{"role", "content"}`` dicts.
            metadata: Optional tags stored alongside.
        """
        if not user_id or not messages or self._unavailable:
            return

        memory = await self._get_memory()
        if memory is None:
            return

        try:
            await memory.add(messages=messages, user_id=user_id, metadata=metadata or {})
            logger.info("memory_added", user_id=user_id, message_count=len(messages))
        except Exception as e:
            # Losing a memory write is invisible to this turn and recoverable on
            # the next one. It must never surface as a failed request.
            logger.exception("memory_add_failed", user_id=user_id, error=str(e))

    def add_in_background(
        self, user_id: str | None, messages: list[dict[str, str]], metadata: dict | None = None
    ) -> None:
        """Schedule a write without awaiting it.

        Keeps a reference to the task: a bare ``create_task`` may be garbage
        collected before it runs, which loses the write silently.

        Args:
            user_id: Owner of the memories.
            messages: The turn to record.
            metadata: Optional tags.
        """
        if not user_id or self._unavailable:
            return

        task = asyncio.create_task(self.add(user_id, messages, metadata))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)


# Strong references to in-flight background writes. Without this the event loop
# holds only a weak reference and a write can vanish mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task] = set()

memory_service = MemoryService()

__all__ = ["NO_MEMORY", "MemoryService", "memory_service"]
