from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar, Token
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from core.agents.state import OrchestrationState

_trace_run_id: ContextVar[str | None] = ContextVar("langfuse_trace_run_id", default=None)
_trace_thread_id: ContextVar[str | None] = ContextVar("langfuse_trace_thread_id", default=None)

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


def set_trace_thread_id(thread_id: str | None) -> Token[str | None]:
    return _trace_thread_id.set(thread_id)


def reset_trace_thread_id(token: Token[str | None]) -> None:
    _trace_thread_id.reset(token)


def get_trace_thread_id() -> str | None:
    return _trace_thread_id.get()


def resolve_subgraph_span_name(node_key: str) -> str:
    return SUBGRAPH_SPAN_NAMES.get(node_key, node_key)


def _run_traced_node(
    node_key: str,
    state: OrchestrationState,
    invoke_fn: Callable[..., dict],
    *invoke_args: Any,
) -> dict:
    from core.observability.langfuse import subgraph_span_context

    run_token = set_trace_run_id(state["run_id"])
    thread_token = set_trace_thread_id(state["thread_id"])
    span_name = resolve_subgraph_span_name(node_key)
    tier = SUBGRAPH_TIERS.get(node_key)
    pending_interrupt: GraphInterrupt | None = None
    try:
        with subgraph_span_context(
            state,
            span_name,
            tier=tier,
            subgraph=node_key,
        ) as span:
            try:
                result = invoke_fn(state, *invoke_args)
            except GraphInterrupt as exc:
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
        reset_trace_thread_id(thread_token)
        reset_trace_run_id(run_token)


def wrap_traced_subgraph_node(
    node_key: str,
    invoke_fn: Callable[..., dict],
    *,
    needs_config: bool = False,
) -> Callable[..., dict]:
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
    from core.observability.langfuse import tavily_tool_span_context

    run_id = get_trace_run_id()
    if run_id is None:
        return nullcontext()
    return tavily_tool_span_context(
        run_id,
        tool_name,
        thread_id=get_trace_thread_id(),
        input_data=input_data,
    )


@contextmanager
def traced_tavily_call(
    tool_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> Iterator[Any]:
    with tavily_mcp_span_context(tool_name, input_data=input_data) as span:
        yield span


def fitness_mcp_span_context(
    tool_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> AbstractContextManager[Any]:
    from core.observability.langfuse import fitness_mcp_tool_span_context

    run_id = get_trace_run_id()
    if run_id is None:
        return nullcontext()
    return fitness_mcp_tool_span_context(
        run_id,
        tool_name,
        thread_id=get_trace_thread_id(),
        input_data=input_data,
    )


@contextmanager
def traced_fitness_mcp_call(
    tool_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> Iterator[Any]:
    with fitness_mcp_span_context(tool_name, input_data=input_data) as span:
        yield span
