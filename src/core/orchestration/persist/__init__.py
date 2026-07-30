"""Deterministic persistence subsystem triggered by supervisor persist_trigger."""

from core.orchestration.persist.node import invoke_persist_node

__all__ = [
    "invoke_persist_node",
]
