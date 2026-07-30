"""Durable run summaries for sidebar history and GET /runs listing.

Unlike RunTracker (in-flight liveness only), rows here survive after a run
settles so the UI can reload the conversation list from the backend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from psycopg_pool import ConnectionPool

RunLifecycleStatus = Literal[
    "running", "waiting_hitl", "completed", "failed", "refused", "not_found"
]

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS run_history (
    run_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS run_history_user_updated_idx
    ON run_history (user_id, updated_at DESC)
"""
_STATUS_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS run_history_status_updated_idx
    ON run_history (status, updated_at)
"""


@dataclass(frozen=True)
class RunSummary:
    """Lightweight run record for history listing."""

    run_id: str
    user_id: str
    query: str
    status: RunLifecycleStatus
    steps: tuple[str, ...]
    updated_at: datetime


class InMemoryRunHistoryStore:
    """Process-local run history for tests and MemorySaver-backed dev runs."""

    def __init__(self) -> None:
        self._rows: dict[str, RunSummary] = {}

    def upsert(
        self,
        *,
        run_id: str,
        user_id: str,
        query: str,
        status: RunLifecycleStatus,
        steps: list[str] | tuple[str, ...],
    ) -> None:
        self._rows[run_id] = RunSummary(
            run_id=run_id,
            user_id=user_id,
            query=query,
            status=status,
            steps=tuple(steps),
            updated_at=datetime.now(tz=UTC),
        )

    def list_by_user(self, user_id: str, *, limit: int = 50) -> list[RunSummary]:
        rows = [row for row in self._rows.values() if row.user_id == user_id]
        rows.sort(key=lambda row: row.updated_at, reverse=True)
        return rows[:limit]

    def list_recent_completed(self, *, since: datetime, limit: int = 50) -> list[RunSummary]:
        rows = [
            row
            for row in self._rows.values()
            if row.status == "completed" and row.updated_at >= since
        ]
        rows.sort(key=lambda row: row.updated_at)
        return rows[:limit]

    def reset(self) -> None:
        self._rows.clear()


class RunHistoryStore:
    """Postgres-backed durable run summaries keyed by user_id."""

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
            conn.execute(_INDEX_DDL)
            conn.execute(_STATUS_INDEX_DDL)
            conn.commit()

    def upsert(
        self,
        *,
        run_id: str,
        user_id: str,
        query: str,
        status: RunLifecycleStatus,
        steps: list[str] | tuple[str, ...],
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO run_history (run_id, user_id, query, status, steps, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, now())
                ON CONFLICT (run_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    query = EXCLUDED.query,
                    status = EXCLUDED.status,
                    steps = EXCLUDED.steps,
                    updated_at = now()
                """,
                (run_id, user_id, query, status, json.dumps(list(steps))),
            )
            conn.commit()

    def list_by_user(self, user_id: str, *, limit: int = 50) -> list[RunSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_id, query, status, steps, updated_at
                FROM run_history
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
        return [
            RunSummary(
                run_id=row[0],
                user_id=row[1],
                query=row[2],
                status=row[3],
                steps=tuple(row[4] or []),
                updated_at=row[5],
            )
            for row in rows
        ]

    def list_recent_completed(self, *, since: datetime, limit: int = 50) -> list[RunSummary]:
        """All users' completed runs updated since `since`, oldest first (so a
        capped batch always makes progress through a backlog instead of
        re-fetching the same newest rows every tick)."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_id, query, status, steps, updated_at
                FROM run_history
                WHERE status = 'completed' AND updated_at >= %s
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (since, limit),
            ).fetchall()
        return [
            RunSummary(
                run_id=row[0],
                user_id=row[1],
                query=row[2],
                status=row[3],
                steps=tuple(row[4] or []),
                updated_at=row[5],
            )
            for row in rows
        ]

    def reset(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE run_history")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
