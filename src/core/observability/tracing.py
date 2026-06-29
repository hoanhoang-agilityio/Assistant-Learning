from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from contextvars import ContextVar, Token
from typing import Any

from core.agents.state import OrchestrationState, RouteDecision

_trace_run_id: ContextVar[str | None] = ContextVar("langfuse_trace_run_id", default=None)

PARTIAL_RERUN_DECISIONS: frozenset[RouteDecision] = frozenset(
    {"FIX_REASONING", "REPLAN", "RERESEARCH"}
)

SUBGRAPH_SPAN_NAMES: dict[str, str] = {
    "planning": "Planning",
    "research": "Research",
    "fitness": "Fitness",
    "verification": "Verification",
    "hitl": "HITL",
    "persist": "PERSIST_RESULTS",
}

SUBGRAPH_TIERS: dict[str, str] = {
    "planning": "XHIGH",
    "verification": "XHIGH",
}


def set_trace_run_id(run_id: str | None) -> Token[str | None]:
    return _trace_run_id.set(run_id)


def reset_trace_run_id(token: Token[str | None]) -> None:
    _trace_run_id.reset(token)


def get_trace_run_id() -> str | None:
    return _trace_run_id.get()


def resolve_subgraph_span_name(node_key: str, route_decision: RouteDecision | None) -> str:
    """Map graph node + route decision to the Langfuse span name."""
    if route_decision == "REPLAN" and node_key == "planning":
        return "partial_rerun_REPLAN"
    if route_decision == "RERESEARCH" and node_key == "research":
        return "partial_rerun_RERESEARCH"
    if route_decision == "FIX_REASONING" and node_key == "fitness":
        return "partial_rerun_FIX_REASONING"
    return SUBGRAPH_SPAN_NAMES.get(node_key, node_key)


def wrap_traced_subgraph_node(
    node_key: str,
    invoke_fn: Callable[[OrchestrationState], dict],
) -> Callable[[OrchestrationState], dict]:
    """Wrap a graph node with run-scoped Langfuse subgraph spans."""
    from core.observability.langfuse import subgraph_span_context

    def traced_node(state: OrchestrationState) -> dict:
        token = set_trace_run_id(state["run_id"])
        span_name = resolve_subgraph_span_name(node_key, state.get("route_decision"))
        tier = SUBGRAPH_TIERS.get(node_key)
        try:
            with subgraph_span_context(
                state,
                span_name,
                tier=tier,
                subgraph=node_key,
                is_partial_rerun=state.get("route_decision") in PARTIAL_RERUN_DECISIONS,
            ) as span:
                result = invoke_fn(state)
                if span is not None:
                    span.update(output=result)
                return result
        finally:
            reset_trace_run_id(token)

    traced_node.__name__ = f"traced_{node_key}_node"
    return traced_node


def tavily_mcp_span_context(
    tool_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> AbstractContextManager[Any]:
    """Open a Tavily MCP child span under the active run trace."""
    from core.observability.langfuse import tavily_tool_span_context

    run_id = get_trace_run_id()
    if run_id is None:
        return nullcontext()
    return tavily_tool_span_context(run_id, tool_name, input_data=input_data)
