from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.llm.serializers import compact_execution_plan_for_llm
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.research.research_agent import run_research_agent
from core.subgraphs.research.state import ResearchState
from core.subgraphs.research.utils import (
    load_execution_plan_for_research,
    load_profile_for_research,
    write_research_artifacts,
)
from core.subgraphs.wrapper import merge_subgraph_updates


def _todos_gate_node(state: ResearchState) -> dict:
    plan = load_execution_plan_for_research(state["workspace_path"])
    if plan is None:
        return {
            "profile": {},
            "execution_plan": {},
            "blocked_by_todos": True,
            "evidence_summary": (
                "Research blocked: plan/execution_plan.json is required before retrieval"
            ),
        }

    profile = load_profile_for_research(state["workspace_path"])
    return {
        "profile": profile,
        "execution_plan": compact_execution_plan_for_llm(plan),
        "blocked_by_todos": False,
    }


def _research_agent_node(state: ResearchState) -> dict:
    execution_plan = load_execution_plan_for_research(state["workspace_path"])
    if execution_plan is None:
        raise ValueError("Research agent invoked without execution plan")
    # GoalSpec is derived exactly once here -- profile was loaded fresh from VFS in
    # _todos_gate_node and never changes again within this subgraph -- and threaded
    # explicitly through run_research_agent's internal call chain from here on.
    goal_spec = derive_goal_spec(state["profile"])
    result = run_research_agent(
        query=state["query"],
        request_type=state["request_type"],
        profile=state["profile"],
        goal_spec=goal_spec,
        execution_plan=execution_plan,
        workspace_path=state["workspace_path"],
        is_reresearch=state.get("is_reresearch", False),
    )
    return {
        "sources": result.sources,
        "evidence": result.evidence,
        "structured_findings": result.structured_findings.model_dump(),
        "evidence_summary": result.evidence_summary,
    }


def _write_artifacts_node(state: ResearchState) -> dict:
    from core.subgraphs.research.schema import ResearchFindings

    structured = ResearchFindings.model_validate(state["structured_findings"])
    write_research_artifacts(
        workspace_path=state["workspace_path"],
        sources=state["sources"],
        evidence=state["evidence"],
        structured_findings=structured,
        evidence_summary=state["evidence_summary"] or "",
    )
    return {}


def _blocked_node(state: ResearchState) -> dict:
    return {"evidence_summary": state["evidence_summary"]}


def _route_after_todos_gate(state: ResearchState) -> str:
    if state["blocked_by_todos"]:
        return "blocked"
    return "research_agent"


def build_research_subgraph() -> CompiledStateGraph:
    """Compile the Research subgraph StateGraph."""
    graph = StateGraph(ResearchState)
    graph.add_node("todos_gate", _todos_gate_node)
    graph.add_node("research_agent", _research_agent_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_node("blocked", _blocked_node)
    graph.add_edge(START, "todos_gate")
    graph.add_conditional_edges(
        "todos_gate",
        _route_after_todos_gate,
        {
            "blocked": "blocked",
            "research_agent": "research_agent",
        },
    )
    graph.add_edge("research_agent", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    graph.add_edge("blocked", END)
    return graph.compile()


@lru_cache
def get_research_subgraph() -> CompiledStateGraph:
    return build_research_subgraph()


def to_research_state(state: OrchestrationState) -> ResearchState:
    return ResearchState(
        query=state["fitness_query"],
        request_type=state["request_type"],
        workspace_path=state["workspace_path"],
        profile={},
        execution_plan={},
        evidence=[],
        sources=[],
        structured_findings=None,
        evidence_summary=None,
        blocked_by_todos=False,
        is_reresearch=state.get("route_decision") == "RERESEARCH",
    )


def invoke_research_subgraph(state: OrchestrationState) -> dict:
    """Run the Research subgraph and map results back to orchestration updates."""
    result = get_research_subgraph().invoke(to_research_state(state))
    steps = ["todos_gate"]
    if result["blocked_by_todos"]:
        steps.append("blocked")
    else:
        steps.extend(["research_agent", "write_artifacts"])
    return merge_subgraph_updates(
        state,
        {
            "current_node": "research",
            "waiting_for_user": result["blocked_by_todos"],
        },
        subgraph="research",
        steps=steps,
    )


class ResearchGraph:
    """LangGraph graph for Research subgraph."""

    def __init__(self) -> None:
        self._graph = get_research_subgraph()

    def invoke(self, state: ResearchState) -> ResearchState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_research_subgraph(state)
