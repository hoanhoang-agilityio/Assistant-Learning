"""Planning agent: turns a profile — or a change request — into a verified draft.

Absorbs what used to be two root nodes. ``patch_plan`` shares every input and
every output with the build path, so ``mode="change"`` is one parameter rather
than a second branch.

Deliberately does **not** re-export the ``tools`` list. Binding a *list* named
``tools`` onto this package would shadow the ``tools`` submodule of the same
name, so ``...agents.planning.tools`` would stop resolving to the module for
anything that patches or reloads it — the same trap ``routing/__init__.py``
records.
"""

from app.core.langgraph.agents.planning.agent import AGENT_NAME, build_planning_agent
from app.core.langgraph.agents.planning.patch import SUPPORTED_CHANGES, patch_plan
from app.core.langgraph.agents.planning.state import PlanningMode, PlanningState

__all__ = [
    "AGENT_NAME",
    "SUPPORTED_CHANGES",
    "PlanningMode",
    "PlanningState",
    "build_planning_agent",
    "patch_plan",
]
