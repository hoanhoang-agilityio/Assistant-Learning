"""Graph runtime resources: the persistence seam and its namespace scheme.

``graph_runtime`` is what the rest of the application imports. It is typed as
``GraphRuntime``, so no caller can accidentally depend on a Postgres-only method and pin the
storage choice by mistake.
"""

from app.core.configs.config import settings
from app.core.langgraph.runtime.backends import build_runtime
from app.core.langgraph.runtime.base import GraphRuntime
from app.core.langgraph.runtime.namespaces import MemoryScope, namespace_for

graph_runtime: GraphRuntime = build_runtime(settings.PERSISTENCE_BACKEND)

__all__ = ["GraphRuntime", "MemoryScope", "graph_runtime", "namespace_for"]
