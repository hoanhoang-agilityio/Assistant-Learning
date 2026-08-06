"""Verification subgraph: scope-driven fan-out to three checks, joined at merge.

The fan-out is a conditional entry edge returning a *list* of node names, which
LangGraph runs concurrently. Which checks run comes from ``scope``, so a `check`
turn about knee pain does not pay for a macro comparison the user never asked.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.verification.nodes import (
    merge_issues,
    verify_injury,
    verify_macro,
    verify_volume,
)
from app.core.langgraph.agents.verification.state import VerifyState
from app.core.logging import logger
from app.schemas.graph import VerifyScope

AGENT_NAME = "verification"

_NODE_FOR_SCOPE: dict[VerifyScope, str] = {
    "macro": "verify_macro",
    "volume": "verify_volume",
    "injury": "verify_injury",
}

# An empty scope means "assess everything". Used by build_plan, change_plan and
# revert, where all three verifiers are mandatory — only
# `check` lets the user's wording narrow it.
_ALL_NODES = tuple(_NODE_FOR_SCOPE.values())


def route_scope(state: VerifyState) -> list[str]:
    """Choose which verifiers run this turn.

    Args:
        state: Current verify state, whose ``scope`` names the enabled checks.

    Returns:
        Node names to run concurrently. Never empty — an empty return would
        strand the graph with ``merge_issues`` waiting on nothing.
    """
    scope = state.get("scope") or []
    nodes = [_NODE_FOR_SCOPE[item] for item in scope if item in _NODE_FOR_SCOPE]
    if not nodes:
        return list(_ALL_NODES)

    logger.info("verification_scope_selected", scope=scope, nodes=nodes)
    return nodes


def build_verification_graph() -> CompiledStateGraph:
    """Compile the verification subgraph.

    Compiled without a checkpointer: the root graph's checkpointer persists the
    whole tree, and a second one would write a competing history.

    Returns:
        The compiled subgraph, named so its spans are identifiable in Langfuse.
    """
    builder = StateGraph(VerifyState)
    builder.add_node("verify_macro", verify_macro, destinations=("merge_issues",))
    builder.add_node("verify_volume", verify_volume, destinations=("merge_issues",))
    builder.add_node("verify_injury", verify_injury, destinations=("merge_issues",))
    builder.add_node("merge_issues", merge_issues, destinations=(END,))

    builder.add_conditional_edges(START, route_scope, list(_ALL_NODES))
    for node in _ALL_NODES:
        builder.add_edge(node, "merge_issues")
    builder.add_edge("merge_issues", END)

    return builder.compile(name=AGENT_NAME)
