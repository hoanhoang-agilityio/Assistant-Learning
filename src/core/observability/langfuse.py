from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from core.agents.state import OrchestrationState
from core.config.settings import Settings, get_settings

_langfuse_client: Langfuse | None = None


def is_langfuse_enabled(settings: Settings | None = None) -> bool:
    resolved = settings or get_settings()
    return bool(resolved.langfuse_public_key and resolved.langfuse_secret_key)


def get_langfuse_client(settings: Settings | None = None) -> Langfuse | None:
    """Return a singleton Langfuse client configured from settings."""
    global _langfuse_client
    resolved = settings or get_settings()
    if not is_langfuse_enabled(resolved):
        return None
    if _langfuse_client is None:
        _langfuse_client = Langfuse(
            public_key=resolved.langfuse_public_key,
            secret_key=resolved.langfuse_secret_key,
            host=resolved.langfuse_host,
        )
    return _langfuse_client


def reset_langfuse_client() -> None:
    """Clear cached client — used in tests."""
    global _langfuse_client
    _langfuse_client = None


def create_trace_id_for_run(run_id: str, settings: Settings | None = None) -> str:
    """Create a deterministic Langfuse trace id seeded by run_id."""
    client = get_langfuse_client(settings)
    if client is None:
        return run_id
    return client.create_trace_id(seed=run_id)


def build_langfuse_callbacks(
    run_id: str,
    *,
    settings: Settings | None = None,
) -> list[CallbackHandler]:
    """Build LangChain callbacks that attach graph execution to a root trace."""
    if not is_langfuse_enabled(settings):
        return []
    trace_id = create_trace_id_for_run(run_id, settings=settings)
    return [
        CallbackHandler(
            trace_context={"trace_id": trace_id},
            update_trace=True,
        )
    ]


def build_graph_invoke_config(
    state: OrchestrationState,
    *,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build LangGraph invoke config with thread_id and Langfuse callbacks."""
    config: dict[str, Any] = {
        "configurable": {"thread_id": state["thread_id"]},
        "metadata": {
            "langfuse_session_id": state["thread_id"],
            "run_id": state["run_id"],
            "langfuse_tags": ["pt-ai-core", "orchestration"],
        },
    }
    callbacks = build_langfuse_callbacks(state["run_id"], settings=settings)
    if callbacks:
        config["callbacks"] = callbacks
    if extra:
        config.update(extra)
    return config


def supervisor_span_context(
    state: OrchestrationState,
    *,
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a supervisor span on the root trace for the current run."""
    client = get_langfuse_client(settings)
    if client is None:
        return nullcontext()
    trace_id = create_trace_id_for_run(state["run_id"], settings=settings)
    return client.start_as_current_span(
        trace_context={"trace_id": trace_id},
        name="supervisor",
        input={
            "query": state["query"],
            "current_node": state["current_node"],
            "route_decision": state["route_decision"],
        },
        metadata={
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
        },
    )


def flush_langfuse(settings: Settings | None = None) -> None:
    """Flush pending Langfuse events — call after graph completion in workers."""
    client = get_langfuse_client(settings)
    if client is not None:
        client.flush()
