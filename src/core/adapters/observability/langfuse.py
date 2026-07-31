from __future__ import annotations

import base64
import logging
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import httpx
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from core.adapters.observability.hierarchy import (
    LANGFUSE_ORCHESTRATION_TAGS,
    LANGFUSE_SESSION_METADATA_KEY,
    LangfuseHierarchyIds,
    langfuse_thread_context,
    map_run_to_trace_seed,
    map_thread_to_session_id,
    resolve_hierarchy_ids,
)
from core.config.settings import Settings, get_settings
from core.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None
_langfuse_disabled: bool = False
_langfuse_disable_reason: str | None = None


def is_langfuse_enabled(settings: Settings | None = None) -> bool:
    resolved = settings or get_settings()
    if _langfuse_disabled:
        return False
    return bool(
        resolved.langfuse_tracing_enabled
        and resolved.langfuse_public_key
        and resolved.langfuse_secret_key
    )


def _disable_langfuse_tracing(reason: str) -> None:
    global _langfuse_disabled, _langfuse_disable_reason, _langfuse_client
    if _langfuse_disabled:
        return
    _langfuse_disabled = True
    _langfuse_disable_reason = reason
    _langfuse_client = None
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    logger.warning("Langfuse tracing disabled: %s", reason)


def reset_langfuse_client() -> None:
    """Clear cached client — used in tests."""
    global _langfuse_client, _langfuse_disabled, _langfuse_disable_reason
    _langfuse_client = None
    _langfuse_disabled = False
    _langfuse_disable_reason = None
    os.environ.pop("LANGFUSE_TRACING_ENABLED", None)


def _build_langfuse_auth_headers(public_key: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "x-langfuse-public-key": public_key,
    }


def verify_langfuse_credentials(settings: Settings) -> tuple[bool, str | None]:
    """Check Langfuse API keys against the configured base URL."""
    public_key = settings.langfuse_public_key
    secret_key = settings.langfuse_secret_key
    if not public_key or not secret_key:
        return False, "Langfuse API keys are not configured"
    base_url = settings.langfuse_base_url.rstrip("/")
    try:
        response = httpx.get(
            f"{base_url}/api/public/projects",
            headers=_build_langfuse_auth_headers(public_key, secret_key),
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        return False, f"Langfuse unreachable at {base_url}: {exc}"
    if response.status_code == 401:
        return (
            False,
            "Langfuse credentials rejected (401 Unauthorized). "
            "Ensure LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY match LANGFUSE_BASE_URL.",
        )
    if response.status_code >= 400:
        return False, f"Langfuse health check failed ({response.status_code}) at {base_url}"
    return True, None


def get_langfuse_client(settings: Settings | None = None) -> Langfuse | None:
    """Return a singleton Langfuse client configured from settings."""
    global _langfuse_client
    if _langfuse_disabled:
        return None
    resolved = settings or get_settings()
    if not is_langfuse_enabled(resolved):
        return None
    if _langfuse_client is None:
        is_valid, error = verify_langfuse_credentials(resolved)
        if not is_valid:
            _disable_langfuse_tracing(error or "Langfuse credentials are invalid")
            return None
        _langfuse_client = Langfuse(
            public_key=resolved.langfuse_public_key,
            secret_key=resolved.langfuse_secret_key,
            host=resolved.langfuse_base_url.rstrip("/"),
        )
    return _langfuse_client


def create_trace_id_for_run(run_id: str, settings: Settings | None = None) -> str:
    """Create a deterministic Langfuse Trace id seeded by ``run_id`` (Run → Trace)."""
    client = get_langfuse_client(settings)
    if client is None:
        return map_run_to_trace_seed(run_id)
    return client.create_trace_id(seed=map_run_to_trace_seed(run_id))


def resolve_run_hierarchy(
    state: OrchestrationState,
    *,
    settings: Settings | None = None,
) -> LangfuseHierarchyIds:
    """Resolve Runs → Traces → Threads ids for ``state`` (trace id may be deterministic)."""
    return resolve_hierarchy_ids(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        trace_id=create_trace_id_for_run(state["run_id"], settings=settings),
    )


def _trace_context(run_id: str, settings: Settings | None = None) -> dict[str, str]:
    return {"trace_id": create_trace_id_for_run(run_id, settings=settings)}


def build_langfuse_callbacks(
    run_id: str,
    *,
    settings: Settings | None = None,
) -> list[CallbackHandler]:
    """Build LangChain callbacks that attach graph execution to a root Trace (Run)."""
    if not is_langfuse_enabled(settings):
        return []
    client = get_langfuse_client(settings)
    if client is None:
        return []
    return [
        CallbackHandler(
            trace_context=_trace_context(run_id, settings=settings),
            update_trace=True,
        )
    ]


def build_graph_invoke_config(
    state: OrchestrationState,
    *,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build LangGraph invoke config with thread_id and Langfuse hierarchy bindings.

    Hierarchy (see ``core.adapters.observability.hierarchy``):
    - ``thread_id`` → Langfuse Session (Thread) via ``langfuse_session_id`` metadata
      (CallbackHandler Sessions write path) and ``propagate_attributes`` on spans
    - ``run_id`` → Langfuse Trace via deterministic ``create_trace_id(seed=run_id)``
    """
    hierarchy = resolve_run_hierarchy(state, settings=settings)
    config: dict[str, Any] = {
        "configurable": {"thread_id": hierarchy.thread_id},
        "metadata": {
            **hierarchy.langfuse_session_metadata,
            "langfuse_tags": list(LANGFUSE_ORCHESTRATION_TAGS),
            "langfuse_trace_id": hierarchy.trace_id,
        },
    }
    callbacks = build_langfuse_callbacks(hierarchy.run_id, settings=settings)
    if callbacks:
        config["callbacks"] = callbacks
    if extra:
        config.update(extra)
    return config


def fetch_langfuse_thread(
    thread_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Fetch a Langfuse Session for an app thread via the public Sessions API.

    Langfuse Sessions are the product "Threads" grouping. Returns ``None`` when
    tracing is disabled, credentials fail, or the session is missing (404).
    """
    resolved = settings or get_settings()
    if not is_langfuse_enabled(resolved):
        return None
    public_key = resolved.langfuse_public_key
    secret_key = resolved.langfuse_secret_key
    if not public_key or not secret_key:
        return None
    session_id = map_thread_to_session_id(thread_id)
    base_url = resolved.langfuse_base_url.rstrip("/")
    try:
        response = httpx.get(
            f"{base_url}/api/public/sessions/{session_id}",
            headers=_build_langfuse_auth_headers(public_key, secret_key),
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("Langfuse Sessions API unreachable for thread %s: %s", thread_id, exc)
        return None
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        logger.warning(
            "Langfuse Sessions API error %s for thread %s",
            response.status_code,
            thread_id,
        )
        return None
    payload = response.json()
    return payload if isinstance(payload, dict) else None


@contextmanager
def _traced_span(
    *,
    run_id: str,
    thread_id: str,
    name: str,
    input_data: dict[str, Any] | None,
    metadata: dict[str, Any],
    settings: Settings | None = None,
) -> Iterator[Any]:
    """Open a span under Run→Trace and bind Thread→Session via propagate_attributes."""
    client = get_langfuse_client(settings)
    if client is None:
        yield None
        return
    with langfuse_thread_context(thread_id, run_id=run_id):
        with client.start_as_current_span(
            trace_context=_trace_context(run_id, settings=settings),
            name=name,
            input=input_data,
            metadata={
                **metadata,
                "run_id": run_id,
                "thread_id": thread_id,
                LANGFUSE_SESSION_METADATA_KEY: map_thread_to_session_id(thread_id),
            },
        ) as span:
            yield span


def supervisor_span_context(
    state: OrchestrationState,
    *,
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a supervisor span on the root Trace, bound to the thread's Langfuse Session."""
    return _traced_span(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        name="Supervisor",
        input_data={
            "query": state["query"],
            "current_node": state["current_node"],
        },
        metadata={"span_type": "supervisor"},
        settings=settings,
    )


def supervisor_routing_span_context(
    state: OrchestrationState,
    *,
    routing_context: dict[str, Any],
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a child span for one Supervisor routing decision (Router Judge proposal +
    Policy Engine verdict), nested under the run's root Trace / thread Session."""
    return _traced_span(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        name="SupervisorRouting",
        input_data=routing_context,
        metadata={"span_type": "supervisor_routing"},
        settings=settings,
    )


def subgraph_span_context(
    state: OrchestrationState,
    span_name: str,
    *,
    tier: str | None = None,
    subgraph: str | None = None,
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a subgraph span on the root Trace, bound to the thread's Langfuse Session."""
    metadata: dict[str, Any] = {
        "subgraph": subgraph,
        "span_type": "subgraph",
    }
    if tier:
        metadata["reasoning_tier"] = tier
    return _traced_span(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        name=span_name,
        input_data={
            "query": state["query"],
            "current_node": state["current_node"],
        },
        metadata=metadata,
        settings=settings,
    )


def tavily_tool_span_context(
    run_id: str,
    tool_name: str,
    *,
    thread_id: str | None = None,
    input_data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a Tavily MCP tool span as a child under the research Trace / Session."""
    resolved_thread_id = thread_id or run_id
    return _traced_span(
        run_id=run_id,
        thread_id=resolved_thread_id,
        name=tool_name,
        input_data=input_data,
        metadata={
            "provider": "tavily-mcp",
            "span_type": "mcp_tool",
        },
        settings=settings,
    )


def fitness_mcp_tool_span_context(
    run_id: str,
    tool_name: str,
    *,
    thread_id: str | None = None,
    input_data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> AbstractContextManager[Any]:
    """Open a Fitness MCP tool span as a child of the current Trace / Session.

    Mirrors ``tavily_tool_span_context`` so a Fitness MCP failure is exactly as
    visible as a Tavily failure, not a blind spot relative to every other external call.
    """
    resolved_thread_id = thread_id or run_id
    return _traced_span(
        run_id=run_id,
        thread_id=resolved_thread_id,
        name=tool_name,
        input_data=input_data,
        metadata={
            "provider": "fitness-mcp",
            "span_type": "mcp_tool",
        },
        settings=settings,
    )


def flush_langfuse(settings: Settings | None = None) -> None:
    """Flush pending Langfuse events — call after graph completion in workers."""
    client = get_langfuse_client(settings)
    if client is not None:
        client.flush()
