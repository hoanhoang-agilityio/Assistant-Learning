"""Postgres-backed daily usage store — shared across horizontally scaled API replicas.

InMemoryUsageStore's counters live in a single process's memory: running more
than one API replica behind a load balancer makes the effective per-user
daily cap `N x configured_limit` instead of the configured value, since each
replica enforces its own independent counter. This store reuses the same
Postgres instance already provisioned for the LangGraph checkpointer
(core.graph.checkpointer.postgres_checkpointer) so the cap is enforced once,
centrally, regardless of which replica handles a given request.
"""

from __future__ import annotations

from datetime import UTC, datetime

from psycopg_pool import ConnectionPool

from core.rate_limit.store import DailyUsage

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_usage_daily (
    user_id TEXT NOT NULL,
    day_key TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day_key)
)
"""


def _row_to_usage(row: tuple[int, int, int, float]) -> DailyUsage:
    request_count, input_tokens, output_tokens, estimated_cost_usd = row
    return DailyUsage(
        request_count=request_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=round(estimated_cost_usd, 8),
    )


class PostgresUsageStore:
    """Postgres-backed daily usage counters keyed by user and UTC date.

    Duck-type compatible with InMemoryUsageStore (same method signatures),
    so it's a drop-in replacement anywhere a usage store is accepted.
    """

    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        # ConnectionPool's own default connection timeout is 30s — too slow
        # for a "fail fast at app startup" guarantee against a misconfigured
        # or unreachable Postgres instance.
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

    @staticmethod
    def day_key(at: datetime | None = None) -> str:
        moment = at or datetime.now(UTC)
        return moment.strftime("%Y-%m-%d")

    def get_usage(self, user_id: str, *, day_key: str | None = None) -> DailyUsage:
        resolved_day = day_key or self.day_key()
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT request_count, input_tokens, output_tokens, estimated_cost_usd
                FROM ai_usage_daily WHERE user_id = %s AND day_key = %s
                """,
                (user_id, resolved_day),
            ).fetchone()
        if row is None:
            return DailyUsage()
        return _row_to_usage(row)

    def increment_requests(self, user_id: str, *, day_key: str | None = None) -> DailyUsage:
        resolved_day = day_key or self.day_key()
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO ai_usage_daily (user_id, day_key, request_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, day_key)
                DO UPDATE SET request_count = ai_usage_daily.request_count + 1
                RETURNING request_count, input_tokens, output_tokens, estimated_cost_usd
                """,
                (user_id, resolved_day),
            ).fetchone()
            conn.commit()
        assert row is not None
        return _row_to_usage(row)

    def record_tokens(
        self,
        user_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        day_key: str | None = None,
    ) -> DailyUsage:
        resolved_day = day_key or self.day_key()
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO ai_usage_daily
                    (user_id, day_key, input_tokens, output_tokens, estimated_cost_usd)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, day_key)
                DO UPDATE SET
                    input_tokens = ai_usage_daily.input_tokens + EXCLUDED.input_tokens,
                    output_tokens = ai_usage_daily.output_tokens + EXCLUDED.output_tokens,
                    estimated_cost_usd =
                        ai_usage_daily.estimated_cost_usd + EXCLUDED.estimated_cost_usd
                RETURNING request_count, input_tokens, output_tokens, estimated_cost_usd
                """,
                (
                    user_id,
                    resolved_day,
                    max(input_tokens, 0),
                    max(output_tokens, 0),
                    max(cost_usd, 0.0),
                ),
            ).fetchone()
            conn.commit()
        assert row is not None
        return _row_to_usage(row)

    def reset(self) -> None:
        """Clear all usage rows — used in tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE ai_usage_daily")
            conn.commit()

    def close(self) -> None:
        self._pool.close()
