from langgraph.graph import END

from core.agents.rerun import MAX_REPLAN_COUNT, MAX_RETRY_COUNT
from core.agents.state import OrchestrationState, RouteDecision

DOMAIN_ORDER = ("planning", "research", "fitness", "verify")
DOMAIN_TO_NODE = {
    "planning": "planning",
    "research": "research",
    "fitness": "fitness",
    "verify": "verification",
}
NODE_TO_DOMAIN = {node: domain for domain, node in DOMAIN_TO_NODE.items()}

_PARTIAL_RERUN_ENTRY_NODES = frozenset({"supervisor", "verification"})


def resolve_next_subgraph(state: OrchestrationState) -> str:
    """Select the next subgraph in the default pipeline order."""
    affected_domains = state["affected_domains"] or list(DOMAIN_ORDER)
    ordered_domains = [domain for domain in DOMAIN_ORDER if domain in affected_domains]
    if not ordered_domains:
        ordered_domains = list(DOMAIN_ORDER)

    current_node = state["current_node"]
    if current_node == "supervisor":
        return DOMAIN_TO_NODE[ordered_domains[0]]

    last_domain = NODE_TO_DOMAIN.get(current_node)
    if last_domain is None:
        return DOMAIN_TO_NODE[ordered_domains[0]]

    try:
        next_index = ordered_domains.index(last_domain) + 1
    except ValueError:
        return DOMAIN_TO_NODE[ordered_domains[0]]

    if next_index >= len(ordered_domains):
        return "hitl"

    return DOMAIN_TO_NODE[ordered_domains[next_index]]


def _resolve_partial_rerun_route(state: OrchestrationState) -> str | None:
    """Route partial reruns and continue downstream after the entry subgraph completes."""
    decision: RouteDecision | None = state["route_decision"]
    current_node = state["current_node"]

    if decision == "FIX_REASONING":
        if state["retry_count"] >= MAX_RETRY_COUNT:
            return "hitl"
        return "fitness"

    if decision == "REPLAN":
        if state["replan_count"] > MAX_REPLAN_COUNT:
            return "hitl"
        if current_node in _PARTIAL_RERUN_ENTRY_NODES:
            return "planning"
        if current_node == "planning":
            return "research"
        if current_node == "research":
            return "fitness"
        return resolve_next_subgraph(state)

    if decision == "RERESEARCH":
        if state["retry_count"] >= MAX_RETRY_COUNT:
            return "hitl"
        if current_node in _PARTIAL_RERUN_ENTRY_NODES:
            return "research"
        if current_node == "research":
            return "fitness"
        return resolve_next_subgraph(state)

    return None


def route_from_supervisor(state: OrchestrationState) -> str:
    """Route from supervisor to the next graph node."""
    if state["waiting_for_user"]:
        return "hitl"

    decision = state["route_decision"]
    approval_status = state["approval_status"]
    if decision == "REFUSED":
        return END

    if decision == "HITL":
        if approval_status == "approved":
            return "persist"
        if approval_status == "rejected":
            return END
        if approval_status == "revision_requested" or state.get("route_decision") == "REPLAN":
            if state["replan_count"] > MAX_REPLAN_COUNT:
                return END
            return "planning"
        return "hitl"

    partial_route = _resolve_partial_rerun_route(state)
    if partial_route is not None:
        return partial_route

    if decision == "COMPLETE":
        if approval_status == "approved":
            return "persist"
        if approval_status == "rejected":
            return END
        if approval_status == "revision_requested" or state.get("route_decision") == "REPLAN":
            if state["replan_count"] > MAX_REPLAN_COUNT:
                return END
            return "planning"
        return "hitl"

    return resolve_next_subgraph(state)
