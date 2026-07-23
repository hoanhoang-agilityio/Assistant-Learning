from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.utils import (
    build_verification_report,
    citation_check_data,
    consistency_check_data,
    heuristic_faithfulness_data,
    load_verification_context,
    safety_check_data,
    write_verification_artifacts,
)
from core.subgraphs.wrapper import merge_subgraph_updates


def _load_context_node(state: VerificationState) -> dict:
    context = load_verification_context(state["workspace_path"])
    return {
        "draft_plan": context["draft_plan"],
        "sources": context["sources"],
        "evidence": context["evidence"],
        "macro_targets": context["macro_targets"],
        "training_plan": context["training_plan"],
        "safety_flags": context["safety_flags"],
        "plan_blueprint": context["plan_blueprint"],
    }


def _citation_check_node(state: VerificationState) -> dict:
    citation = citation_check_data(state["draft_plan"], state["sources"])
    return {"verification_report": {"citation": citation}}


def _consistency_check_node(state: VerificationState) -> dict:
    consistency = consistency_check_data(
        state["draft_plan"],
        state["macro_targets"],
        state["training_plan"],
        state["plan_blueprint"],
    )
    report = dict(state["verification_report"])
    report["consistency"] = consistency
    return {"verification_report": report}


def _safety_check_node(state: VerificationState) -> dict:
    safety = safety_check_data(state["draft_plan"], state["safety_flags"])
    report = dict(state["verification_report"])
    report["safety"] = safety
    return {"verification_report": report}


def _ragas_faithfulness_node(state: VerificationState) -> dict:
    ragas = heuristic_faithfulness_data(state["draft_plan"], state["evidence"])
    report = dict(state["verification_report"])
    report["ragas"] = ragas
    final_report = build_verification_report(
        citation=report["citation"],
        consistency=report["consistency"],
        safety=report["safety"],
        ragas=ragas,
    )
    return {
        "verification_report": final_report,
        "faithfulness_score": ragas["faithfulness_score"],
    }


def _write_artifacts_node(state: VerificationState) -> dict:
    ragas = state["verification_report"]["ragas"]
    write_verification_artifacts(
        workspace_path=state["workspace_path"],
        verification_report=state["verification_report"],
        ragas=ragas,
    )
    return {}


def build_verification_subgraph() -> CompiledStateGraph:
    """Compile the Verification subgraph StateGraph."""
    graph = StateGraph(VerificationState)
    graph.add_node("load_context", _load_context_node)
    graph.add_node("citation_check", _citation_check_node)
    graph.add_node("consistency_check", _consistency_check_node)
    graph.add_node("safety_check", _safety_check_node)
    graph.add_node("ragas_faithfulness", _ragas_faithfulness_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "citation_check")
    graph.add_edge("citation_check", "consistency_check")
    graph.add_edge("consistency_check", "safety_check")
    graph.add_edge("safety_check", "ragas_faithfulness")
    graph.add_edge("ragas_faithfulness", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    return graph.compile()


@lru_cache
def get_verification_subgraph() -> CompiledStateGraph:
    return build_verification_subgraph()


def to_verification_state(state: OrchestrationState) -> VerificationState:
    return VerificationState(
        workspace_path=state["workspace_path"],
        draft_plan="",
        sources=[],
        evidence=[],
        macro_targets={},
        training_plan={},
        safety_flags=[],
        plan_blueprint={},
        verification_report={},
        faithfulness_score=None,
    )


def invoke_verification_subgraph(state: OrchestrationState) -> dict:
    """Run the Verification subgraph and map results back to orchestration updates."""
    result = get_verification_subgraph().invoke(to_verification_state(state))
    report = result["verification_report"]
    return merge_subgraph_updates(
        state,
        {
            "current_node": "verification",
            "verification_passed": report["passed"],
            "faithfulness_score": result["faithfulness_score"],
        },
        subgraph="verification",
        steps=[
            "load_context",
            "citation_check",
            "consistency_check",
            "safety_check",
            "ragas_faithfulness",
            "write_artifacts",
        ],
    )


class VerificationGraph:
    """LangGraph graph for Verification subgraph."""

    def __init__(self) -> None:
        self._graph = get_verification_subgraph()

    def invoke(self, state: VerificationState) -> VerificationState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_verification_subgraph(state)
