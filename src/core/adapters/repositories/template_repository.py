"""Postgres persistence for cached workout templates.

Pure CRUD, no DDL at construction (schema must already exist -- see
core.adapters.repositories.bootstrap). Replaces the file-backed TemplateRegistry.
"""

from typing import Any

from psycopg.types.json import Json
from psycopg_pool import ConnectionPool


class TemplateRepository:
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

    def get(self, fingerprint: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT workout FROM fitness_kb_templates WHERE fingerprint = %s",
                (fingerprint,),
            ).fetchone()
        return row[0] if row is not None else None

    def put(self, fingerprint: str, workout: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO fitness_kb_templates (fingerprint, workout, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (fingerprint) DO UPDATE SET
                    workout = EXCLUDED.workout,
                    updated_at = now()
                """,
                (fingerprint, Json(workout)),
            )
            conn.commit()

    def reset(self) -> None:
        """Clear all rows -- used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE fitness_kb_templates")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
