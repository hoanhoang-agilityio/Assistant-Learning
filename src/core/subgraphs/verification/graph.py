from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.tools import (
    citation_check,
    consistency_check,
    ragas_faithfulness,
    safety_check,
)
from core.subgraphs.verification.utils import (
    build_verification_report,
    load_verification_context,
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
        "profile": context["profile"],
        "constraints": context["constraints"],
        "safety_flags": context["safety_flags"],
    }


def _citation_check_node(state: VerificationState) -> dict:
    citation = citation_check.invoke(
        {
            "draft_plan": state["draft_plan"],
            "sources": state["sources"],
        }
    )
    return {"verification_report": {"citation": citation}}


def _consistency_check_node(state: VerificationState) -> dict:
    consistency = consistency_check.invoke(
        {
            "draft_plan": state["draft_plan"],
            "macro_targets": state["macro_targets"],
            "training_plan": state["training_plan"],
        }
    )
    report = dict(state["verification_report"])
    report["consistency"] = consistency
    return {"verification_report": report}


def _safety_check_node(state: VerificationState) -> dict:
    safety = safety_check.invoke(
        {
            "draft_plan": state["draft_plan"],
            "profile": state["profile"],
            "constraints": state["constraints"],
            "safety_flags": state["safety_flags"],
        }
    )
    report = dict(state["verification_report"])
    report["safety"] = safety
    return {"verification_report": report}


def _ragas_faithfulness_node(state: VerificationState) -> dict:
    ragas = ragas_faithfulness.invoke(
        {
            "draft_plan": state["draft_plan"],
            "evidence": state["evidence"],
        }
    )
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
        "pass_fail": ragas["pass_fail"],
        "feedback": final_report["feedback"],
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
        profile=state["user_profile"],
        constraints=state["constraints"],
        safety_flags=[],
        verification_report={},
        feedback=None,
        faithfulness_score=None,
        pass_fail=False,
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
