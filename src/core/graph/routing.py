from core.agents.rerun import MAX_REPLAN_COUNT, MAX_RETRY_COUNT
from core.agents.state import OrchestrationState

DOMAIN_ORDER = ("planning", "research", "fitness", "verify")
DOMAIN_TO_NODE = {
    "planning": "planning",
    "research": "research",
    "fitness": "fitness",
    "verify": "verification",
}
NODE_TO_DOMAIN = {node: domain for domain, node in DOMAIN_TO_NODE.items()}


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


def route_from_supervisor(state: OrchestrationState) -> str:
    """Route from supervisor to the next graph node."""
    if state["waiting_for_user"]:
        return "hitl"

    decision = state["route_decision"]
    if decision == "HITL":
        return "hitl"
    if decision == "FIX_REASONING":
        if state["retry_count"] >= MAX_RETRY_COUNT:
            return "hitl"
        return "fitness"
    if decision == "REPLAN":
        if state["replan_count"] >= MAX_REPLAN_COUNT:
            return "hitl"
        return "planning"
    if decision == "RERESEARCH":
        if state["retry_count"] >= MAX_RETRY_COUNT:
            return "hitl"
        return "research"
    if decision == "COMPLETE":
        if state["approval_status"] == "approved":
            return "persist"
        return "hitl"

    return resolve_next_subgraph(state)
