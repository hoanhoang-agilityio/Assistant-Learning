"""Agent registry — the only module that enumerates the full set of agents.

Adding an agent is a new package plus one line here. If it also requires editing
the root graph, a schema and a route, the seam is in the wrong place.

Agents named here are built once during ``create_graph()`` and cached; building
a subgraph per request is a real cost.
"""

from collections.abc import Callable

from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.ingest import build_ingest_graph
from app.core.langgraph.agents.planning import build_planning_graph
from app.core.langgraph.agents.profile import build_profile_graph
from app.core.langgraph.agents.qa import build_qa_graph
from app.core.langgraph.agents.verification import build_verification_graph

AGENTS: dict[str, Callable[[], CompiledStateGraph]] = {
    "ingest": build_ingest_graph,
    "planning": build_planning_graph,
    "profile": build_profile_graph,
    "qa": build_qa_graph,
    "verification": build_verification_graph,
}

__all__ = ["AGENTS"]
