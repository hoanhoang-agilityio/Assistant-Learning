"""Per-LLM-call metrics collection for payload audits and regression guardrails."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage

from core.llm.payload import compact_json
from core.rate_limit.limiter import (
    estimate_message_tokens,
    extract_cached_tokens,
    extract_token_usage,
)
from core.rate_limit.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)

PIPELINE_NODE_ORDER: tuple[str, ...] = (
    "Extract",
    "Planning",
    "Research",
    "Fitness",
    "Verification",
    "Evaluation",
)

_PIPELINE_NODE_ALIASES: dict[str, str] = {
    "profile_extraction": "Extract",
    "planning_agent": "Planning",
    "research_query_planning": "Research",
    "research_react_loop": "Research",
    "research_evidence_eval": "Research",
    "research_synthesis": "Research",
    "fitness_planner": "Fitness",
}

_current_node: ContextVar[str | None] = ContextVar("llm_metrics_node", default=None)
_recorded_metrics: list[LlmCallMetric] = []


@dataclass(frozen=True)
class LlmCallMetric:
    """Single LLM invocation measurement."""

    node: str
    model: str
    estimated_input_tokens: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: float
    payload_chars: int
    largest_payload_keys: list[str]
    source: str = "runtime"


@dataclass
class LlmMetricsCollector:
    """In-memory collector for LLM call metrics (tests and debug runs)."""

    metrics: list[LlmCallMetric] = field(default_factory=list)

    def record(self, metric: LlmCallMetric) -> None:
        self.metrics.append(metric)

    def clear(self) -> None:
        self.metrics.clear()

    def summary_by_node(self) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[LlmCallMetric]] = {}
        for metric in self.metrics:
            grouped.setdefault(metric.node, []).append(metric)
        summary: dict[str, dict[str, Any]] = {}
        for node, items in grouped.items():
            summary[node] = {
                "model": items[-1].model,
                "calls": len(items),
                "input_tokens": sum(item.input_tokens for item in items),
                "output_tokens": sum(item.output_tokens for item in items),
                "cached_tokens": sum(item.cached_tokens for item in items),
                "estimated_input_tokens": sum(item.estimated_input_tokens for item in items),
                "latency_ms": round(sum(item.latency_ms for item in items), 2),
                "source": items[-1].source,
            }
        return summary

    def to_table_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "node": metric.node,
                "model": metric.model,
                "input_tokens": metric.input_tokens,
                "output_tokens": metric.output_tokens,
                "cached_tokens": metric.cached_tokens,
                "latency_ms": round(metric.latency_ms, 2),
                "calls": 1,
                "source": metric.source,
            }
            for metric in self.metrics
        ]

    def summary_by_pipeline_node(self) -> dict[str, dict[str, Any]]:
        """Aggregate token usage and estimated cost by high-level pipeline node."""
        grouped: dict[str, dict[str, Any]] = {
            node: {
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
                "calls": 0,
            }
            for node in PIPELINE_NODE_ORDER
        }
        for metric in self.metrics:
            pipeline_node = _PIPELINE_NODE_ALIASES.get(metric.node)
            if pipeline_node is None:
                continue
            bucket = grouped[pipeline_node]
            bucket["input_tokens"] += metric.input_tokens
            bucket["output_tokens"] += metric.output_tokens
            bucket["cached_tokens"] += metric.cached_tokens
            bucket["tokens"] += metric.input_tokens + metric.output_tokens
            bucket["cost_usd"] = round(
                bucket["cost_usd"]
                + estimate_cost_usd(
                    metric.model,
                    input_tokens=metric.input_tokens,
                    output_tokens=metric.output_tokens,
                ),
                8,
            )
            bucket["calls"] += 1
        return grouped

    def pipeline_cost_table(self) -> list[dict[str, Any]]:
        """Return pipeline rows with token totals and percentage share."""
        summary = self.summary_by_pipeline_node()
        total_tokens = sum(item["tokens"] for item in summary.values())
        rows: list[dict[str, Any]] = []
        for node in PIPELINE_NODE_ORDER:
            item = summary[node]
            tokens = int(item["tokens"])
            percent = round((tokens / total_tokens) * 100, 1) if total_tokens else 0.0
            rows.append(
                {
                    "node": node,
                    "tokens": tokens,
                    "input_tokens": int(item["input_tokens"]),
                    "output_tokens": int(item["output_tokens"]),
                    "cached_tokens": int(item["cached_tokens"]),
                    "cost_usd": float(item["cost_usd"]),
                    "percent": percent,
                    "calls": int(item["calls"]),
                }
            )
        rows.append(
            {
                "node": "Total",
                "tokens": total_tokens,
                "input_tokens": sum(row["input_tokens"] for row in rows),
                "output_tokens": sum(row["output_tokens"] for row in rows),
                "cached_tokens": sum(row["cached_tokens"] for row in rows),
                "cost_usd": round(sum(row["cost_usd"] for row in rows), 8),
                "percent": 100.0 if total_tokens else 0.0,
                "calls": sum(row["calls"] for row in rows),
            }
        )
        return rows


_collector = LlmMetricsCollector()


def get_llm_metrics_collector() -> LlmMetricsCollector:
    return _collector


def reset_llm_metrics() -> None:
    _collector.clear()
    global _recorded_metrics
    _recorded_metrics = []


def set_llm_metrics_node(node: str | None) -> Token[str | None]:
    return _current_node.set(node)


def reset_llm_metrics_node(token: Token[str | None]) -> None:
    _current_node.reset(token)


def _largest_payload_keys(messages: list[BaseMessage], limit: int = 5) -> list[str]:
    sizes: list[tuple[str, int]] = []
    for message in messages:
        content = getattr(message, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            sizes.append(("message", len(content)))
            continue
        if isinstance(payload, dict):
            for key, value in payload.items():
                sizes.append((key, len(compact_json(value))))
    sizes.sort(key=lambda item: item[1], reverse=True)
    return [key for key, _size in sizes[:limit]]


def record_llm_call_metric(
    *,
    messages: list[BaseMessage],
    response: Any,
    model_name: str,
    estimated_input_tokens: int,
    latency_ms: float,
    node: str | None = None,
    source: str = "runtime",
) -> LlmCallMetric:
    """Record a single LLM call metric when payload debug or collection is enabled."""
    resolved_node = node or _current_node.get() or "unknown"
    input_tokens, output_tokens = extract_token_usage(
        response,
        estimated_input_tokens=estimated_input_tokens,
    )
    cached_tokens = extract_cached_tokens(response)
    payload_chars = sum(
        len(str(getattr(message, "content", "")))
        for message in messages
        if isinstance(getattr(message, "content", ""), str)
    )
    metric = LlmCallMetric(
        node=resolved_node,
        model=model_name,
        estimated_input_tokens=estimated_input_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        latency_ms=latency_ms,
        payload_chars=payload_chars,
        largest_payload_keys=_largest_payload_keys(messages),
        source=source,
    )
    _collector.record(metric)
    _recorded_metrics.append(metric)
    return metric


def estimate_payload_tokens(messages: list[BaseMessage]) -> int:
    """Estimate input tokens for a message list."""
    return estimate_message_tokens(messages)


def format_pipeline_cost_table_markdown(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
) -> str:
    """Render the pipeline token-cost table as markdown."""
    lines = [
        f"# Token usage — {run_id}",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "| Node | Tokens | % |",
        "| --- | ---: | ---: |",
    ]
    for row in rows:
        node = str(row["node"])
        if node == "Total":
            lines.append(f"| **{node}** | **{row['tokens']:,}** | **{row['percent']:.1f}** |")
            continue
        lines.append(f"| {node} | {row['tokens']:,} | {row['percent']:.1f} |")
    total_row = next((row for row in rows if row["node"] == "Total"), None)
    if total_row is not None:
        input_tokens = total_row["input_tokens"]
        cached_tokens = total_row.get("cached_tokens", 0)
        cache_hit_rate = (cached_tokens / input_tokens * 100) if input_tokens else 0.0
        lines.extend(
            [
                "",
                f"Input tokens: {input_tokens:,}",
                f"Output tokens: {total_row['output_tokens']:,}",
                f"Cached input tokens: {cached_tokens:,} ({cache_hit_rate:.1f}% of input)",
                f"Estimated cost (USD): ${total_row['cost_usd']:.6f}",
                f"LLM calls: {total_row['calls']}",
            ]
        )
    return "\n".join(lines) + "\n"


def format_pipeline_cost_table_log(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
) -> str:
    """Render a plain-text version of the pipeline token-cost table."""
    lines = [
        f"Token usage — {run_id}",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        f"{'Node':<14} {'Tokens':>10} {'%':>6}",
        f"{'-' * 14} {'-' * 10} {'-' * 6}",
    ]
    for row in rows:
        node = str(row["node"])
        lines.append(f"{node:<14} {int(row['tokens']):>10,} {float(row['percent']):>5.1f}")
    total_row = next((row for row in rows if row["node"] == "Total"), None)
    if total_row is not None:
        input_tokens = total_row["input_tokens"]
        cached_tokens = total_row.get("cached_tokens", 0)
        cache_hit_rate = (cached_tokens / input_tokens * 100) if input_tokens else 0.0
        lines.extend(
            [
                "",
                f"Input tokens: {input_tokens:,}",
                f"Output tokens: {total_row['output_tokens']:,}",
                f"Cached input tokens: {cached_tokens:,} ({cache_hit_rate:.1f}% of input)",
                f"Estimated cost (USD): ${total_row['cost_usd']:.6f}",
                f"LLM calls: {total_row['calls']}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_pipeline_cost_log(
    workspace_path: str,
    *,
    run_id: str,
) -> str:
    """Write token usage summary artifacts to the run workspace."""
    rows = get_llm_metrics_collector().pipeline_cost_table()
    markdown = format_pipeline_cost_table_markdown(run_id=run_id, rows=rows)
    plain = format_pipeline_cost_table_log(run_id=run_id, rows=rows)
    log_dir = Path(workspace_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "token_cost.md").write_text(markdown, encoding="utf-8")
    (log_dir / "token_cost.log").write_text(plain, encoding="utf-8")
    logger.info("Token usage summary for %s:\n%s", run_id, plain.rstrip())
    return str(log_dir / "token_cost.log")
