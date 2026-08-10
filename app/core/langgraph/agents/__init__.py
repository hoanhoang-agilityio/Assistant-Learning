"""Agent registry — the only module that enumerates the full set of agents.

Adding an agent is a new package plus one line here. If it also requires editing
the supervisor, a schema and a route, the seam is in the wrong place.

What earns a place in ``agents/``: an independent workflow or capability with
its own state and contract, worth packaging and developing on its own. A run of
linear steps that exists only to orchestrate the turn is middleware or a tool
body instead — ``routing/`` and ``profile/`` both sit outside this registry for
that reason, now because they are middleware rather than because they were root
nodes (``docs/supervisor-architecture.md`` §12).

Three names. ``planning`` is a ``create_agent`` loop rather than a fixed
pipeline, ``review`` is what ``ingest`` became, and ``qa`` is unchanged.
``verification`` is not among them and is not a graph at all: it is the pure
functions in ``core/langgraph/checks/``, called from
``core/langgraph/scoring.py`` inside tool bodies. It was a ``StateGraph`` for
its fan-out, and the fan-out was never worth its own topology.

Agents are built once, on first use, and cached. Building a subgraph per request
is a real cost, and under a supervisor the same agent may be invoked several
times in one turn.
"""

from collections.abc import Callable

from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.planning import build_planning_agent
from app.core.langgraph.agents.qa import build_qa_agent
from app.core.langgraph.agents.review import build_review_agent

AGENTS: dict[str, Callable[[], CompiledStateGraph]] = {
    "planning": build_planning_agent,
    "review": build_review_agent,
    "qa": build_qa_agent,
}

_built: dict[str, CompiledStateGraph] = {}


def get_agent(name: str) -> CompiledStateGraph:
    """Return a compiled agent, building it on first use.

    Args:
        name: A key of :data:`AGENTS`.

    Returns:
        The compiled agent.

    Raises:
        KeyError: When no agent is registered under that name, which is a bug
            rather than a runtime branch.
    """
    if name not in _built:
        _built[name] = AGENTS[name]()
    return _built[name]


def build_all() -> dict[str, CompiledStateGraph]:
    """Build every registered agent.

    Called once at startup so the first user turn does not pay for compilation.

    Returns:
        Every agent, keyed by name.
    """
    return {name: get_agent(name) for name in AGENTS}


__all__ = ["AGENTS", "build_all", "get_agent"]
