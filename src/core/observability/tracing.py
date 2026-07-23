from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar, Token
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

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


def _run_traced_node(
    node_key: str,
    state: OrchestrationState,
    invoke_fn: Callable[..., dict],
    *invoke_args: Any,
) -> dict:
    from core.observability.langfuse import subgraph_span_context

    token = set_trace_run_id(state["run_id"])
    span_name = resolve_subgraph_span_name(node_key, state.get("route_decision"))
    tier = SUBGRAPH_TIERS.get(node_key)
    is_partial_rerun = span_name.startswith("partial_rerun_")
    pending_interrupt: GraphInterrupt | None = None
    try:
        with subgraph_span_context(
            state,
            span_name,
            tier=tier,
            subgraph=node_key,
            is_partial_rerun=is_partial_rerun,
        ) as span:
            try:
                result = invoke_fn(state, *invoke_args)
            except GraphInterrupt as exc:
                # A node (currently only "user") can pause mid-execution via LangGraph's
                # dynamic interrupt(), which raises rather than returning. That is expected,
                # benign control flow — not a failure. Swallow inside this span so OTEL /
                # Langfuse do not mark the observation ERROR on context exit, then re-raise
                # after the span closes so the parent graph still pauses.
                pending_interrupt = exc
                if span is not None:
                    span.update(
                        output={"paused": True, "reason": "interrupt"},
                        level="DEFAULT",
                        status_message="paused for interrupt",
                    )
            else:
                if span is not None:
                    span.update(output=result)
                return result
        assert pending_interrupt is not None
        raise pending_interrupt
    finally:
        reset_trace_run_id(token)


def wrap_traced_subgraph_node(
    node_key: str,
    invoke_fn: Callable[..., dict],
    *,
    needs_config: bool = False,
) -> Callable[..., dict]:
    """Wrap a graph node with run-scoped Langfuse subgraph spans.

    Set `needs_config=True` for a node whose `invoke_fn` takes `(state, config)` -- e.g. the
    User subgraph, which needs the parent's config forwarded through for its `interrupt()`/
    resume support (see `core.subgraphs.user.graph.invoke_user_subgraph`). LangGraph decides
    whether to pass a config based on the wrapped node function's own signature, so the two
    cases need genuinely different closures here, not just a runtime branch.
    """
    if needs_config:

        def traced_node_with_config(state: OrchestrationState, config: RunnableConfig) -> dict:
            return _run_traced_node(node_key, state, invoke_fn, config)

        traced_node_with_config.__name__ = f"traced_{node_key}_node"
        return traced_node_with_config

    def traced_node(state: OrchestrationState) -> dict:
        return _run_traced_node(node_key, state, invoke_fn)

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


@contextmanager
def traced_tavily_call(
    tool_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a Tavily span and allow callers to attach output before it closes."""
    with tavily_mcp_span_context(tool_name, input_data=input_data) as span:
        yield span
