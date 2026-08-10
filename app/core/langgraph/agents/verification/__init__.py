"""Verification agent: scores a plan against the rubrics, blind to how it was built.

Deliberately not an agent in the ``create_agent`` sense
(``docs/supervisor-architecture.md`` §8). It is a ``StateGraph`` — a conditional
entry edge fanning out to three checks, joined at ``merge_issues`` — and it is
reachable only from tool bodies (``commit_draft``, ``score_plan``), never from a
supervisor tool call.

Giving a model any part of rubric scoring would make MRV and MEV negotiable.
They are not.
"""

from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.verification.graph import AGENT_NAME, build_verification_graph
from app.core.langgraph.agents.verification.nodes import sort_issues
from app.core.langgraph.agents.verification.state import VerifyState

_graph: CompiledStateGraph | None = None


def get_verification_graph() -> CompiledStateGraph:
    """Return the compiled verification graph, building it on first use.

    Cached at module level rather than held by the root agent, because the
    callers are now plain functions inside tool bodies rather than nodes that
    were handed a built subgraph. Compiling per call is a real cost on the
    repair loop, which runs this graph once per attempt.

    Returns:
        The compiled verification graph.
    """
    global _graph
    if _graph is None:
        _graph = build_verification_graph()
    return _graph


__all__ = [
    "AGENT_NAME",
    "VerifyState",
    "build_verification_graph",
    "get_verification_graph",
    "sort_issues",
]
