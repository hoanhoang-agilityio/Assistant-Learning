"""Deterministic persistence subsystem triggered by supervisor persist_trigger."""

from core.persist.node import invoke_persist_node

__all__ = [
    "invoke_persist_node",
]
