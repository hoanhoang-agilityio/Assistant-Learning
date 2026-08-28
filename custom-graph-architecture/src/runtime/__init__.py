"""Graph runtime resources: the persistence seam and its namespace scheme.

``graph_runtime`` is what the rest of the application imports. It is typed as
``GraphRuntime``, so no caller can accidentally depend on a Postgres-only method and pin the
storage choice by mistake.
"""

from src.configs.config import settings
from src.runtime.backends import build_runtime
from src.runtime.base import GraphRuntime
from src.runtime.namespaces import MemoryScope, namespace_for, plan_namespace

graph_runtime: GraphRuntime = build_runtime(settings.PERSISTENCE_BACKEND)

__all__ = [
    "GraphRuntime",
    "MemoryScope",
    "graph_runtime",
    "namespace_for",
    "plan_namespace",
]
