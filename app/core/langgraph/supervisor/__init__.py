"""The supervisor: middleware for what must always run, tools for what may.

Deliberately does **not** re-export the ``tools`` list. Binding a *list* named
``tools`` onto this package would shadow the ``tools`` submodule of the same
name, so ``...supervisor.tools`` would stop resolving to the module for anything
that patches or reloads it — the same trap ``routing/__init__.py`` records.
"""

from app.core.langgraph.supervisor.agent import (
    AGENT_NAME,
    build_supervisor,
    build_supervisor_with,
    interrupt_question,
)
from app.core.langgraph.supervisor.middleware import OFF_TOPIC_ANSWER
from app.core.langgraph.supervisor.state import NEW_TURN, SupervisorState
from app.core.langgraph.supervisor.tools import WRITE_TOOLS

__all__ = [
    "AGENT_NAME",
    "NEW_TURN",
    "OFF_TOPIC_ANSWER",
    "WRITE_TOOLS",
    "SupervisorState",
    "build_supervisor",
    "build_supervisor_with",
    "interrupt_question",
]
