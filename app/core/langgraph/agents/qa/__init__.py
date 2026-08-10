"""General-QA agent: answers knowledge questions without touching the plan.

Deliberately does **not** re-export the ``tools`` list. Binding a *list* named
``tools`` onto this package would shadow the ``tools`` submodule of the same
name, so ``...agents.qa.tools`` would stop resolving to the module for
anything that patches or reloads it — the same trap ``routing/__init__.py``
records.
"""

from app.core.langgraph.agents.qa.graph import (
    AGENT_NAME,
    EXHAUSTED_ANSWER,
    FAILURE_ANSWER,
    build_qa_agent,
)
from app.core.langgraph.agents.qa.state import QAState
from app.core.langgraph.agents.qa.tools import estimate_macros

__all__ = [
    "AGENT_NAME",
    "EXHAUSTED_ANSWER",
    "FAILURE_ANSWER",
    "QAState",
    "build_qa_agent",
    "estimate_macros",
]
