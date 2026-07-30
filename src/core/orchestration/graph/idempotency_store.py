"""Maps a client-supplied idempotency key to the run it originally created, so
a duplicate create_run request (client retry after a dropped response,
double-click, at-least-once delivery) returns the existing run instead of
starting a second one.

Mirrors core.orchestration.graph.run_tracker.RunTracker / core.adapters.rate_limit.postgres_store
.PostgresUsageStore's shape: a small, single-table, psycopg_pool-backed
store, created with CREATE TABLE IF NOT EXISTS rather than a migration
framework -- consistent with this repo's other custom Postgres tables.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS run_idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class IdempotencyStore:
    """Postgres-backed idempotency_key -> run_id mapping, unique on the key."""

    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self._pool = ConnectionPool(
            conninfo,
            min_size=min_size,
            max_size=max_size,
            timeout=connect_timeout_seconds,
            open=True,
        )
        with self._pool.connection() as conn:
            conn.execute(_TABLE_DDL)
            conn.commit()

    def get_or_create(self, idempotency_key: str, run_id: str) -> tuple[str, bool]:
        """Atomically claim idempotency_key for run_id, or return the run_id
        an earlier request already claimed it for.

        Returns (resolved_run_id, created). created is True only when this
        call is the one that claimed the key -- the caller should start a new
        run for run_id. created is False when a prior request already owns
        this key; resolved_run_id is that prior run's id and run_id (the
        caller's freshly generated candidate) must be discarded unused,
        rather than a second run ever being started for the same key.
        """
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO run_idempotency_keys (idempotency_key, run_id)
                VALUES (%s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING run_id
                """,
                (idempotency_key, run_id),
            ).fetchone()
            if row is not None:
                conn.commit()
                return row[0], True
            # The unique constraint means whatever row conflicted with us is
            # already durably committed by the request that inserted it --
            # this SELECT cannot race the conflict we just observed.
            existing = conn.execute(
                "SELECT run_id FROM run_idempotency_keys WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
            conn.commit()
        assert existing is not None
        return existing[0], False

    def reset(self) -> None:
        """Clear all mappings -- used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE run_idempotency_keys")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
