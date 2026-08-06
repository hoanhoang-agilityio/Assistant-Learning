"""Short-lived cache in front of memory search.

Two backends behind one interface. ``VALKEY_HOST`` set → Valkey/Redis, shared
across instances so a horizontally-scaled deployment gets one cache rather than
N. Unset → an in-process TTL cache, which is correct for a single process and
means local development needs no extra service.

**Every failure degrades to a miss.** A cache exists to make something faster;
if it cannot, the caller must still get an answer. A `get` that raises would
turn a Valkey restart into failed chat turns, which is strictly worse than the
uncached latency it was meant to avoid.
"""

from typing import Any

from cachetools import TTLCache

from app.core.configs.config import settings
from app.core.logging import logger

# Entries are keyed by a hash of (user, query) and expire quickly, so the bound
# only matters as a memory ceiling for the in-process backend.
_MAX_LOCAL_ENTRIES = 2048


class CacheService:
    """Key/value cache with a TTL, backed by Valkey or by memory."""

    def __init__(self) -> None:
        """Prepare a lazily-connected cache."""
        self._client: Any = None
        self._local: TTLCache[str, str] = TTLCache(
            maxsize=_MAX_LOCAL_ENTRIES, ttl=settings.CACHE_TTL_SECONDS
        )
        self._initialised = False

    @property
    def backend(self) -> str:
        """Name the active backend, for logs and health output.

        Returns:
            ``"valkey"`` or ``"memory"``.
        """
        return "valkey" if self._client is not None else "memory"

    async def initialize(self) -> None:
        """Connect to Valkey when configured, otherwise stay in process.

        Called from the application lifespan. A connection failure is logged and
        the service falls back to the in-process cache rather than preventing
        startup — the app is fully functional without a cache.
        """
        if self._initialised:
            return
        self._initialised = True

        if not settings.VALKEY_HOST:
            logger.info("cache_using_in_process_backend", ttl=settings.CACHE_TTL_SECONDS)
            return

        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                db=settings.VALKEY_DB,
                password=settings.VALKEY_PASSWORD or None,
                max_connections=settings.VALKEY_MAX_CONNECTIONS,
                decode_responses=True,
            )
            await self._client.ping()
            logger.info("cache_connected_to_valkey", host=settings.VALKEY_HOST)
        except Exception as e:
            self._client = None
            logger.warning(
                "cache_valkey_unavailable_using_memory",
                host=settings.VALKEY_HOST,
                error=str(e),
            )

    async def get(self, key: str) -> str | None:
        """Read a value.

        Args:
            key: Cache key.

        Returns:
            The cached value, or ``None`` on a miss or any backend error.
        """
        if self._client is None:
            return self._local.get(key)

        try:
            return await self._client.get(key)
        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Write a value with an expiry.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Lifetime in seconds. Defaults to ``CACHE_TTL_SECONDS``.
        """
        if self._client is None:
            self._local[key] = value
            return

        try:
            await self._client.set(key, value, ex=ttl or settings.CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))

    async def close(self) -> None:
        """Release the Valkey connection pool at shutdown."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.warning("cache_close_failed", error=str(e))
            self._client = None
        self._local.clear()
        self._initialised = False


cache_service = CacheService()

__all__ = ["CacheService", "cache_service"]
