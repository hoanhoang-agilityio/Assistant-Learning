from core.agents.state import OrchestrationState
from core.agents.tools import classify_request, route_subgraph


def supervisor_node(state: OrchestrationState) -> dict:
    """Run supervisor orchestration tools and prepare the next routing decision."""
    updates: dict = {}

    if state["request_type"] is None:
        classification = classify_request.invoke(
            {
                "query": state["query"],
                "user_profile": state["user_profile"],
                "constraints": state["constraints"],
            }
        )
        updates.update(classification)

    merged_state: OrchestrationState = {**state, **updates}  # type: ignore[typeddict-item]

    if merged_state["current_node"] == "verification" and merged_state["verification_passed"]:
        updates["route_decision"] = "COMPLETE"

    route_decision = merged_state.get("route_decision")
    if route_decision == "COMPLETE" and merged_state["approval_status"] != "approved":
        updates["waiting_for_user"] = True

    route_subgraph.invoke(
        {
            "route_decision": merged_state.get("route_decision"),
            "affected_domains": merged_state["affected_domains"],
            "current_node": merged_state["current_node"],
        }
    )

    return updates
