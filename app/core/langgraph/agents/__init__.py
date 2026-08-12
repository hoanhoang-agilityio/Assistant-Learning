"""Agent registry — the only module that enumerates the full set of agents."""

from collections.abc import Callable

from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.planning import build_planning_agent
from app.core.langgraph.agents.qa import qa_agent
from app.core.langgraph.agents.review import review_agent

AGENTS: dict[str, Callable[[], CompiledStateGraph]] = {
    "planning": build_planning_agent,
    "review": review_agent,
    "qa": qa_agent,
}

_built: dict[str, CompiledStateGraph] = {}


def get_agent(name: str) -> CompiledStateGraph:
    """Return a compiled agent, building it on first use."""
    if name not in _built:
        _built[name] = AGENTS[name]()
    return _built[name]


def build_all() -> dict[str, CompiledStateGraph]:
    """Build every registered agent.

    Called once at startup so the first user turn does not pay for compilation.

    """
    return {name: get_agent(name) for name in AGENTS}


__all__ = ["AGENTS", "build_all", "get_agent"]
