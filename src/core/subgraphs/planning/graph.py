from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.profile.goal_spec import derive_goal_spec_fields
from core.profile.store import load_run_profile
from core.subgraphs.planning.planning_agent import (
    generate_execution_plan,
    is_planning_agent_overridden,
)
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.templates import build_template_execution_plan
from core.subgraphs.planning.utils import (
    load_revision_feedback,
    persist_execution_plan,
    should_reuse_execution_plan,
)
from core.subgraphs.wrapper import merge_subgraph_updates


def generate_plan(
    profile: dict[str, Any],
    query: str,
    request_type: str | None,
    workspace_path: str,
    constraints: dict[str, Any] | None = None,
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    """Generate a structured execution plan via template or Planning Agent.

    Relocated from ``planning.tools.generate_plan`` (was a ``@tool`` wrapper never bound to
    an LLM -- always called directly via ``.invoke()`` from a deterministic node); logic
    unchanged, now a plain function called directly by ``_generate_plan_node``. Lives here
    (not in utils.py) to avoid a circular import: it needs `planning_agent.py`, which itself
    imports from `utils.py`.
    """
    enriched_profile = {**profile, **derive_goal_spec_fields(profile)}
    template_plan = build_template_execution_plan(enriched_profile)
    if (
        template_plan is not None
        and enriched_profile.get("feasibility_level") != "unsafe"
        and not is_planning_agent_overridden()
        and not (revision_feedback or "").strip()
    ):
        return persist_execution_plan(enriched_profile, template_plan, workspace_path)
    plan = generate_execution_plan(
        profile=enriched_profile,
        query=query,
        request_type=request_type,
        constraints=constraints or {},
        revision_feedback=revision_feedback,
    )
    return persist_execution_plan(enriched_profile, plan, workspace_path)


def _generate_plan_node(state: PlanningState) -> dict:
    return generate_plan(
        profile=load_run_profile(state["workspace_path"]),
        query=state["query"],
        request_type=state["request_type"],
        workspace_path=state["workspace_path"],
        revision_feedback=state.get("revision_feedback"),
    )


def _reuse_execution_plan_node(state: PlanningState) -> dict:
    return {"reused_execution_plan": True}


def _route_entry(state: PlanningState) -> str:
    if should_reuse_execution_plan(
        state.get("route_decision"),
        state["workspace_path"],
        load_run_profile(state["workspace_path"]),
    ):
        return "reuse_execution_plan"
    return "generate_plan"


def build_planning_subgraph() -> CompiledStateGraph:
    """Compile the Planning subgraph StateGraph.

    Profile extraction/validation moved to the User subgraph (see core.subgraphs.user);
    Planning trusts the VFS profile (`plan/profile.json`, loaded via `load_run_profile`) is
    already complete and valid by the time it runs (enforced by the top-level routing guard),
    so it's a fixed two-node sequence with no HITL branch of its own.
    """
    graph = StateGraph(PlanningState)
    graph.add_node("generate_plan", _generate_plan_node)
    graph.add_node("reuse_execution_plan", _reuse_execution_plan_node)
    graph.add_conditional_edges(
        START,
        _route_entry,
        {
            "generate_plan": "generate_plan",
            "reuse_execution_plan": "reuse_execution_plan",
        },
    )
    graph.add_edge("generate_plan", END)
    graph.add_edge("reuse_execution_plan", END)
    return graph.compile()


@lru_cache
def get_planning_subgraph() -> CompiledStateGraph:
    return build_planning_subgraph()


def to_planning_state(state: OrchestrationState) -> PlanningState:
    workspace_path = state["workspace_path"]
    revision_feedback = state.get("revision_feedback") or load_revision_feedback(workspace_path)
    return PlanningState(
        query=state["fitness_query"],
        request_type=state["request_type"],
        workspace_path=workspace_path,
        route_decision=state.get("route_decision"),
        revision_feedback=revision_feedback,
        reused_execution_plan=False,
    )


def _planning_steps_from_result(result: dict) -> list[str]:
    if result.get("reused_execution_plan"):
        return ["reuse_execution_plan"]
    return ["generate_plan"]


def invoke_planning_subgraph(state: OrchestrationState) -> dict:
    """Run the Planning subgraph and map results back to orchestration updates."""
    result = get_planning_subgraph().invoke(to_planning_state(state))
    return merge_subgraph_updates(
        state,
        {"current_node": "planning"},
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
