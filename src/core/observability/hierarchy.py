"""LangFuse hierarchy mapping: Runs → Traces → Threads (Sessions).

Product / orchestration concepts map onto Langfuse data-model concepts as follows:

```text
App concept              Langfuse concept           Identifier
───────────────────────  ─────────────────────────  ─────────────────────────────
Thread (conversation)    Session ("thread" in UI)   session_id == thread_id
Run (one graph invoke)   Trace                      trace_id seeded from run_id
Node / MCP tool / LLM    Observation (span, etc.)   nested under the run's trace
```

Langfuse has no separate "Threads" resource. Conversation grouping is the
**Sessions** API / `session_id` attribute
(https://langfuse.com/docs/observability/features/sessions). This module is the
single source of truth for that mapping and for binding `session_id` via
``propagate_attributes`` (the SDK Sessions write path).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Final

from langfuse import propagate_attributes

LANGFUSE_ORCHESTRATION_TAGS: Final[tuple[str, ...]] = ("pt-ai-core", "orchestration")

# Metadata key consumed by langfuse.langchain.CallbackHandler → session_id attribute.
LANGFUSE_SESSION_METADATA_KEY: Final[str] = "langfuse_session_id"


@dataclass(frozen=True, slots=True)
class LangfuseHierarchyIds:
    """Resolved Langfuse identifiers for one orchestration run inside a thread."""

    run_id: str
    thread_id: str
    trace_id: str
    session_id: str

    @property
    def langfuse_session_metadata(self) -> dict[str, str]:
        """CallbackHandler metadata that maps the app thread onto a Langfuse Session."""
        return {
            LANGFUSE_SESSION_METADATA_KEY: self.session_id,
            "run_id": self.run_id,
            "thread_id": self.thread_id,
        }


def map_thread_to_session_id(thread_id: str) -> str:
    """Map an app ``thread_id`` to the Langfuse Session id (Threads grouping)."""
    return thread_id


def map_run_to_trace_seed(run_id: str) -> str:
    """Seed used with ``Langfuse.create_trace_id(seed=...)`` for a deterministic Trace."""
    return run_id


def resolve_hierarchy_ids(
    *,
    run_id: str,
    thread_id: str,
    trace_id: str | None = None,
) -> LangfuseHierarchyIds:
    """Build the Runs → Traces → Threads identifier bundle for instrumentation."""
    session_id = map_thread_to_session_id(thread_id)
    return LangfuseHierarchyIds(
        run_id=run_id,
        thread_id=thread_id,
        trace_id=trace_id or map_run_to_trace_seed(run_id),
        session_id=session_id,
    )


def hierarchy_propagation_metadata(ids: LangfuseHierarchyIds) -> dict[str, str]:
    """String-only metadata for ``propagate_attributes`` (Langfuse requires str values)."""
    return {
        "run_id": ids.run_id,
        "thread_id": ids.thread_id,
        "langfuse_trace_seed": map_run_to_trace_seed(ids.run_id),
        "langfuse_session_id": ids.session_id,
    }


@contextmanager
def langfuse_thread_context(
    thread_id: str,
    *,
    run_id: str,
    tags: tuple[str, ...] = LANGFUSE_ORCHESTRATION_TAGS,
) -> Iterator[LangfuseHierarchyIds]:
    """Bind Langfuse Session (Thread) attributes for all nested observations.

    Uses the explicit Sessions write path (``propagate_attributes(session_id=...)``)
    so spans created inside this context are grouped under the thread's Session,
    not only via CallbackHandler metadata.
    """
    ids = resolve_hierarchy_ids(run_id=run_id, thread_id=thread_id)
    with propagate_attributes(
        session_id=ids.session_id,
        metadata=hierarchy_propagation_metadata(ids),
        tags=list(tags),
    ):
        yield ids


def optional_langfuse_thread_context(
    thread_id: str | None,
    *,
    run_id: str | None,
    enabled: bool,
) -> AbstractContextManager[LangfuseHierarchyIds | None]:
    """No-op when tracing is off or ids are missing; otherwise ``langfuse_thread_context``."""
    if not enabled or not thread_id or not run_id:
        return nullcontext(None)
    return langfuse_thread_context(thread_id, run_id=run_id)


def describe_hierarchy_mapping() -> dict[str, Any]:
    """Machine-readable Runs → Traces → Threads mapping for docs and tests."""
    return {
        "thread": {
            "app_field": "thread_id",
            "langfuse_concept": "session",
            "langfuse_attribute": "session_id",
            "callback_metadata_key": LANGFUSE_SESSION_METADATA_KEY,
            "api": "GET /api/public/sessions/{sessionId}",
            "note": "Langfuse Sessions are conversation Threads; there is no separate Threads resource.",
        },
        "run": {
            "app_field": "run_id",
            "langfuse_concept": "trace",
            "langfuse_attribute": "trace_id",
            "seed": "create_trace_id(seed=run_id)",
            "api": "GET /api/public/traces/{traceId}",
        },
        "observation": {
            "app_fields": ["subgraph node", "MCP tool", "LLM generation"],
            "langfuse_concept": "observation",
            "parent": "trace",
            "session_inheritance": "via propagate_attributes(session_id=thread_id)",
        },
        "hierarchy": "Session(thread_id) 1—* Trace(run_id) 1—* Observation(span)",
    }
