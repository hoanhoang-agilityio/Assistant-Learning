"""Tracks in-flight background runs so a restarted (or still-running) process
can reconcile orphaned work -- runs whose backing process died mid-execution
and would otherwise be stuck reporting "running" forever, since nothing else
in this codebase persists that a run is actively executing (LangGraph's
checkpoint records state, not liveness).

Mirrors core.adapters.rate_limit.postgres_store.PostgresUsageStore's shape: a small,
single-table, psycopg_pool-backed store, created with CREATE TABLE IF NOT
EXISTS rather than a migration framework, consistent with this repo's only
other custom Postgres table.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS orchestration_runs (
    run_id TEXT PRIMARY KEY,
    query TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    error_class TEXT,
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class RunTracker:
    """Postgres-backed record of runs currently executing in a background thread.

    A row exists only while its run is actively executing: mark_running()
    inserts/refreshes it when background execution starts, clear() removes it
    once execution settles normally (success or an already-handled failure) --
    see RunOrchestrator's _execute_* methods. A row still present with a stale
    updated_at means the process executing it died before reaching clear();
    reconcile_orphaned_runs() is what detects and resolves that.
    """

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

    def mark_running(self, run_id: str, *, query: str) -> None:
        """Record that run_id's background execution has started (or restarted)."""
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO orchestration_runs (run_id, query, status, updated_at)
                VALUES (%s, %s, 'running', now())
                ON CONFLICT (run_id) DO UPDATE SET
                    query = EXCLUDED.query,
                    status = 'running',
                    error_class = NULL,
                    error_message = NULL,
                    updated_at = now()
                """,
                (run_id, query),
            )
            conn.commit()

    def clear(self, run_id: str) -> None:
        """Remove run_id's tracking row once its background execution settles normally."""
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM orchestration_runs WHERE run_id = %s", (run_id,))
            conn.commit()

    def mark_waiting(self, run_id: str, *, query: str) -> None:
        """Record that run_id has settled into a resumable, waiting-for-user state.

        Kept (not deleted, unlike clear()) precisely so claim_resume() has a
        row to atomically transition -- a run can legitimately sit waiting
        for hours or days; reconcile_orphaned_runs()'s WHERE status='running'
        clause already never touches rows in this state.
        """
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO orchestration_runs (run_id, query, status, updated_at)
                VALUES (%s, %s, 'waiting_hitl', now())
                ON CONFLICT (run_id) DO UPDATE SET
                    query = EXCLUDED.query,
                    status = 'waiting_hitl',
                    error_class = NULL,
                    error_message = NULL,
                    updated_at = now()
                """,
                (run_id, query),
            )
            conn.commit()

    def claim_resume(self, run_id: str) -> bool:
        """Atomically transition run_id from 'waiting_hitl' to 'running'.

        One atomic UPDATE ... WHERE status = 'waiting_hitl' -- no version
        column, no optimistic-locking retry loop: the conditional UPDATE
        itself is what makes this safe under concurrent callers (two workers
        resuming the same run, a client retry racing the original request).
        Returns True only for the caller that actually transitioned the row
        (resuming may proceed); False means it was no longer 'waiting_hitl'
        -- another caller already resumed it, or no such row exists -- and
        the caller must not resume the run.
        """
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE orchestration_runs
                SET status = 'running', updated_at = now()
                WHERE run_id = %s AND status = 'waiting_hitl'
                RETURNING run_id
                """,
                (run_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def reconcile_orphaned_runs(self, *, stale_after_seconds: float) -> list[tuple[str, str]]:
        """Mark every run still 'running' past the staleness window as orphaned.

        One atomic UPDATE -- safe to call concurrently (multiple replicas, or a
        periodic timer racing a startup sweep) with no leader election or
        distributed coordination: a conditional UPDATE only ever matches and
        changes a given row once, regardless of how many callers race on it.
        No automatic retry -- a row this marks stays 'failed' with
        error_class='orphaned'; nothing here ever re-attempts the run.

        Returns (run_id, query) for every row this call actually orphaned, so
        the caller can surface each one as a failed run.
        """
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                UPDATE orchestration_runs
                SET status = 'failed',
                    error_class = 'orphaned',
                    error_message = 'Run orphaned: no update since ' || updated_at::text
                WHERE status = 'running'
                  AND updated_at < now() - make_interval(secs => %s)
                RETURNING run_id, query
                """,
                (stale_after_seconds,),
            ).fetchall()
            conn.commit()
        return list(rows)

    def reset(self) -> None:
        """Clear all tracked rows -- used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE orchestration_runs")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
