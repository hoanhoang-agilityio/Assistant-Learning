from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.tools import extract_profile, generate_plan, validate_profile
from core.subgraphs.planning.utils import (
    load_execution_plan_from_vfs,
    load_revision_feedback,
    profile_to_orchestration_updates,
    should_reuse_execution_plan,
    should_use_llm_profile_extraction,
)
from core.subgraphs.wrapper import merge_subgraph_updates


def _extract_profile_node(state: PlanningState) -> dict:
    used_llm_extraction = should_use_llm_profile_extraction(
        state["user_profile"], state["constraints"]
    )
    result = extract_profile.invoke(
        {
            "query": state["query"],
            "user_profile": state["user_profile"],
            "constraints": state["constraints"],
            "revision_feedback": state.get("revision_feedback"),
        }
    )
    return {
        "profile": result["profile"],
        "user_profile": {},
        "constraints": {},
        "used_llm_extraction": used_llm_extraction,
        "requires_tool_approval": False,
    }


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
            "workspace_path": state["workspace_path"],
            "revision_feedback": state.get("revision_feedback"),
        }
    )


def _reuse_execution_plan_node(state: PlanningState) -> dict:
    return {
        **load_execution_plan_from_vfs(state["workspace_path"]),
        "reused_execution_plan": True,
    }


def _planning_hitl_node(state: PlanningState) -> dict:
    return {
        "requires_hitl": True,
    }


def _route_after_validate(state: PlanningState) -> str:
    if state["requires_hitl"]:
        return "planning_hitl"
    if should_reuse_execution_plan(
        state.get("route_decision"),
        state["workspace_path"],
        state["profile"],
    ):
        return "reuse_execution_plan"
    return "generate_plan"


def build_planning_subgraph() -> CompiledStateGraph:
    """Compile the Planning subgraph StateGraph."""
    graph = StateGraph(PlanningState)
    graph.add_node("extract_profile", _extract_profile_node)
    graph.add_node("validate_profile", _validate_profile_node)
    graph.add_node("generate_plan", _generate_plan_node)
    graph.add_node("reuse_execution_plan", _reuse_execution_plan_node)
    graph.add_node("planning_hitl", _planning_hitl_node)
    graph.add_edge(START, "extract_profile")
    graph.add_edge("extract_profile", "validate_profile")
    graph.add_conditional_edges(
        "validate_profile",
        _route_after_validate,
        {
            "planning_hitl": "planning_hitl",
            "generate_plan": "generate_plan",
            "reuse_execution_plan": "reuse_execution_plan",
        },
    )
    graph.add_edge("generate_plan", END)
    graph.add_edge("reuse_execution_plan", END)
    graph.add_edge("planning_hitl", END)
    return graph.compile()


@lru_cache
def get_planning_subgraph() -> CompiledStateGraph:
    return build_planning_subgraph()


def to_planning_state(state: OrchestrationState) -> PlanningState:
    workspace_path = state["workspace_path"]
    revision_feedback = state.get("revision_feedback") or load_revision_feedback(workspace_path)
    return PlanningState(
        query=state["query"],
        user_profile=state["user_profile"],
        constraints=state["constraints"],
        request_type=state["request_type"],
        workspace_path=workspace_path,
        route_decision=state.get("route_decision"),
        revision_feedback=revision_feedback,
        profile={},
        missing_fields=[],
        requires_hitl=False,
        approved_tools=list(state.get("approved_tools") or []),
        used_llm_extraction=False,
        requires_tool_approval=False,
        reused_execution_plan=False,
    )


def _planning_steps_from_result(result: dict) -> list[str]:
    steps = ["extract_profile", "validate_profile"]
    if result.get("requires_hitl"):
        steps.append("planning_hitl")
        return steps
    if result.get("reused_execution_plan"):
        steps.append("reuse_execution_plan")
        return steps
    steps.append("generate_plan")
    return steps


def invoke_planning_subgraph(state: OrchestrationState) -> dict:
    """Run the Planning subgraph and map results back to orchestration updates."""
    result = get_planning_subgraph().invoke(to_planning_state(state))
    profile = result.get("profile", {})
    sync = profile_to_orchestration_updates(
        profile,
        missing_fields=result.get("missing_fields") if result.get("requires_hitl") else [],
    )
    updates: dict = {
        "current_node": "planning",
        "user_profile": sync["user_profile"],
        "constraints": {**state["constraints"], **sync["constraints"]},
    }
    if result.get("requires_hitl"):
        updates["waiting_for_user"] = True
    return merge_subgraph_updates(
        state,
        updates,
        subgraph="planning",
        steps=_planning_steps_from_result(result),
    )


class PlanningGraph:
    """LangGraph planning for Planning subgraph."""

    def __init__(self) -> None:
        self._graph = get_planning_subgraph()

    def invoke(self, state: PlanningState) -> PlanningState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_planning_subgraph(state)
