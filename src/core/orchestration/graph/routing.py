from langgraph.graph import END

from core.orchestration.agents.state import OrchestrationState


def route_from_supervisor(state: OrchestrationState) -> str:
    """Single routing decision point for the whole graph (see docs/reports plan).

    `supervisor_node` always computes `next_agent` -- either "finish" (mapped to
    END here) or a capability name already validated by the Policy Engine
    (`core.orchestration.routing.policy_engine.enforce_routing_invariants`). A scope-refused
    request short-circuits before any routing decision is made (`supervisor_node`
    returns `run_complete=True` directly), which is the only case `next_agent` can
    be missing here.
    """
    next_agent = state.get("next_agent")
    if next_agent is None:
        return END
    return END if next_agent == "finish" else next_agent
