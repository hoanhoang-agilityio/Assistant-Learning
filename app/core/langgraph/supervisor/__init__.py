"""The supervisor: middleware for what must always run, tools for what may.

Deliberately does **not** re-export the ``tools`` list. Binding a *list* named
``tools`` onto this package would shadow the ``tools`` submodule of the same
name, so ``...supervisor.tools`` would stop resolving to the module for anything
that patches or reloads it — the same trap ``routing/__init__.py`` records.
"""

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "AGENT_NAME": "app.core.langgraph.supervisor.agent",
    "NEW_TURN": "app.core.langgraph.supervisor.state",
    "OFF_TOPIC_ANSWER": "app.core.langgraph.supervisor.middleware",
    "SupervisorState": "app.core.langgraph.supervisor.state",
    "WRITE_TOOLS": "app.core.langgraph.supervisor.tools",
    "build_supervisor_with": "app.core.langgraph.supervisor.agent",
    "interrupt_question": "app.core.langgraph.supervisor.agent",
}


def __getattr__(name: str) -> Any:
    """Load public supervisor symbols without eager package side effects."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = [
    "AGENT_NAME",
    "NEW_TURN",
    "OFF_TOPIC_ANSWER",
    "WRITE_TOOLS",
    "SupervisorState",
    "build_supervisor_with",
    "interrupt_question",
]
