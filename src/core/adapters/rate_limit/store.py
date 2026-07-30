from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@dataclass
class DailyUsage:
    """Aggregated per-user usage for a UTC day."""

    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class UsageStore(Protocol):
    """Interface shared by InMemoryUsageStore and PostgresUsageStore."""

    def get_usage(self, user_id: str, *, day_key: str | None = None) -> DailyUsage: ...

    def increment_requests(self, user_id: str, *, day_key: str | None = None) -> DailyUsage: ...

    def record_tokens(
        self,
        user_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        day_key: str | None = None,
    ) -> DailyUsage: ...

    def reset(self) -> None: ...

    @staticmethod
    def day_key(at: datetime | None = None) -> str: ...


class InMemoryUsageStore:
    """Thread-safe in-memory daily usage counters keyed by user and UTC date."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._usage: dict[tuple[str, str], DailyUsage] = {}

    @staticmethod
    def day_key(at: datetime | None = None) -> str:
        moment = at or datetime.now(UTC)
        return moment.strftime("%Y-%m-%d")

    def get_usage(self, user_id: str, *, day_key: str | None = None) -> DailyUsage:
        resolved_day = day_key or self.day_key()
        with self._lock:
            usage = self._usage.get((user_id, resolved_day))
            if usage is None:
                return DailyUsage()
            return DailyUsage(
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
            )

    def increment_requests(self, user_id: str, *, day_key: str | None = None) -> DailyUsage:
        resolved_day = day_key or self.day_key()
        with self._lock:
            usage = self._usage.setdefault((user_id, resolved_day), DailyUsage())
            usage.request_count += 1
            return DailyUsage(
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
            )

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
        with self._lock:
            usage = self._usage.setdefault((user_id, resolved_day), DailyUsage())
            usage.input_tokens += max(input_tokens, 0)
            usage.output_tokens += max(output_tokens, 0)
            usage.estimated_cost_usd = round(usage.estimated_cost_usd + max(cost_usd, 0.0), 8)
            return DailyUsage(
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
            )

    def reset(self) -> None:
        with self._lock:
            self._usage.clear()
