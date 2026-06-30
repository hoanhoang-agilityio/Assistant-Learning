from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.profile.labels import format_missing_profile_prompt
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.tools import extract_profile, generate_plan, validate_profile
from core.subgraphs.planning.utils import profile_to_orchestration_updates


def _extract_profile_node(state: PlanningState) -> dict:
    result = extract_profile.invoke(
        {
            "query": state["query"],
            "user_profile": state["user_profile"],
            "constraints": state["constraints"],
        }
    )
    return {"profile": result["profile"]}


def _validate_profile_node(state: PlanningState) -> dict:
    result = validate_profile.invoke({"profile": state["profile"]})
    return {
        "missing_fields": result["missing_fields"],
        "requires_hitl": result["requires_hitl"],
    }


def _generate_plan_node(state: PlanningState) -> dict:
    return generate_plan.invoke(
        {
            "profile": state["profile"],
            "query": state["query"],
            "request_type": state["request_type"],
            "constraints": state["constraints"],
            "workspace_path": state["workspace_path"],
        }
    )


def _planning_hitl_node(state: PlanningState) -> dict:
    return {
        "requires_hitl": True,
        "planning_output": format_missing_profile_prompt(state["missing_fields"]),
    }


def _route_after_validate(state: PlanningState) -> str:
    if state["missing_fields"]:
        return "planning_hitl"
    return "generate_plan"


def build_planning_subgraph() -> CompiledStateGraph:
    """Compile the Planning subgraph StateGraph."""
    graph = StateGraph(PlanningState)
    graph.add_node("extract_profile", _extract_profile_node)
    graph.add_node("validate_profile", _validate_profile_node)
    graph.add_node("generate_plan", _generate_plan_node)
    graph.add_node("planning_hitl", _planning_hitl_node)
    graph.add_edge(START, "extract_profile")
    graph.add_edge("extract_profile", "validate_profile")
    graph.add_conditional_edges(
        "validate_profile",
        _route_after_validate,
        {
            "planning_hitl": "planning_hitl",
            "generate_plan": "generate_plan",
        },
    )
    graph.add_edge("generate_plan", END)
    graph.add_edge("planning_hitl", END)
    return graph.compile()


@lru_cache
def get_planning_subgraph() -> CompiledStateGraph:
    return build_planning_subgraph()


def to_planning_state(state: OrchestrationState) -> PlanningState:
    return PlanningState(
        query=state["query"],
        user_profile=state["user_profile"],
        constraints=state["constraints"],
        request_type=state["request_type"],
        workspace_path=state["workspace_path"],
        profile={},
        missing_fields=[],
        todos=[],
        execution_plan={},
        planning_output=None,
        requires_hitl=False,
    )


def invoke_planning_subgraph(state: OrchestrationState) -> dict:
    """Run the Planning subgraph and map results back to orchestration updates."""
    result = get_planning_subgraph().invoke(to_planning_state(state))
    profile = result.get("profile", {})
    sync = profile_to_orchestration_updates(
        profile,
        missing_fields=result.get("missing_fields") if result["requires_hitl"] else [],
    )
    updates: dict = {
        "current_node": "planning",
        "user_profile": sync["user_profile"],
        "constraints": {**state["constraints"], **sync["constraints"]},
    }
    if result["requires_hitl"]:
        updates["waiting_for_user"] = True
    return updates


class PlanningGraph:
    """LangGraph planning for Planning subgraph."""

    def __init__(self) -> None:
        self._graph = get_planning_subgraph()

    def invoke(self, state: PlanningState) -> PlanningState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_planning_subgraph(state)
