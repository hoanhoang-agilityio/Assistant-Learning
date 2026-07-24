from langgraph.graph import END

from core.agents.rerun import MAX_REPLAN_COUNT, MAX_RETRY_COUNT
from core.agents.run_execution_plan import RunExecutionPlan
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

# Nodes that assume a complete, valid user profile -- gated by the User subgraph.
_PROFILE_GATED_NODES = frozenset({"planning", "research", "fitness"})

# NOTE on the "guard at START" requirement: there is deliberately no separate conditional
# edge on START routing straight into "user". Off-topic queries must be classified and
# refused by `supervisor_node` (check_topic_scope/classify_request) before any profile
# gating applies -- a query that's off-topic should never be forced through profile intake.
# Since START always goes to "supervisor" first, and `route_from_supervisor`'s REFUSED
# check runs before its profile-gate check, one guard (below) correctly covers both the
# first pass through supervisor and every later one, without ever bypassing classification.


def _profile_ready(state: OrchestrationState) -> bool:
    return bool(state["profile_complete"] and state["profile_valid"])


def _entry_domain(state: OrchestrationState) -> str | None:
    """`RunExecutionPlan.entry_domain` when a plan is present in state, else `None` (the
    caller falls back to its own literal default).

    Phase 3 of the intent-aware orchestration refactor (see
    docs/reports/execution_plan_refactor/). Shared by both retry-target read sites below
    so the `if execution_plan present: read plan; else: literal fallback` pattern exists
    once, not twice.
    """
    execution_plan = state.get("execution_plan")
    if not execution_plan:
        return None
    return RunExecutionPlan.model_validate(execution_plan).entry_domain


def resolve_next_subgraph(state: OrchestrationState) -> str:
    """Select the next subgraph in the default pipeline order."""
    execution_plan = state.get("execution_plan")
    if execution_plan:
        # Phase 3: RunExecutionPlan.ordered_domains is the routing-authoritative source
        # when present -- see docs/reports/execution_plan_refactor/phase_3_technical_spec.md.
        ordered_domains = list(RunExecutionPlan.model_validate(execution_plan).ordered_domains)
    else:
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
            return _entry_domain(state) or "planning"
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


def _route_terminal_decision(state: OrchestrationState) -> str:
    """Shared HITL/COMPLETE routing: approved -> persist, rejected -> END, a revision
    request -> planning (bounded by MAX_REPLAN_COUNT), otherwise -> hitl.

    Collapses what used to be two structurally-identical branches (one per decision value)
    in `route_from_supervisor`.
    """
    approval_status = state["approval_status"]
    if approval_status == "approved":
        return "persist"
    if approval_status == "rejected":
        return END
    if approval_status == "revision_requested":
        if state["replan_count"] > MAX_REPLAN_COUNT:
            return END
        return _entry_domain(state) or "planning"
    return "hitl"


def route_from_supervisor(state: OrchestrationState) -> str:
    """Route from supervisor to the next graph node.

    Defensive guard: whatever target the decision logic below picks, if it's a
    profile-gated node (planning/research/fitness) and the profile isn't complete & valid,
    redirect into the User subgraph first -- covers both the first pass through supervisor
    for a brand new run and a later mid-conversation revision that may have touched the
    profile (see `core.graph.service` setting `profile_complete=False` on revision).
    """
    if state["waiting_for_user"]:
        return "hitl"

    decision = state["route_decision"]
    if decision == "REFUSED":
        return END

    if decision in ("HITL", "COMPLETE"):
        target = _route_terminal_decision(state)
    else:
        partial_route = _resolve_partial_rerun_route(state)
        target = partial_route if partial_route is not None else resolve_next_subgraph(state)

    if target in _PROFILE_GATED_NODES and not _profile_ready(state):
        return "user"
    return target
