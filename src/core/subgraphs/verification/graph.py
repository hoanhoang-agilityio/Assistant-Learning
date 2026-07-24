from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.run_execution_plan import RunExecutionPlan
from core.agents.state import OrchestrationState
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.strategies import (
    ALL_VALIDATOR_STEPS,
    ValidatorStep,
    resolve_strategy,
)
from core.subgraphs.verification.utils import (
    build_verification_report_for_checks,
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
        "safety_flags": context["safety_flags"],
        "plan_blueprint": context["plan_blueprint"],
    }


def _make_validator_node(step: ValidatorStep):
    def _node(state: VerificationState) -> dict:
        result = step.run(state)
        report = dict(state["verification_report"])
        report[step.report_key] = result
        return {"verification_report": report}

    return _node


def _route_after_load_context(state: VerificationState) -> str:
    strategy = resolve_strategy(state.get("verification_strategy"), state.get("workspace_path"))
    return strategy[0].node_name


def _route_after_validator(state: VerificationState) -> str:
    """Generic dispatcher (Phase 5/6): walk this run's verification_strategy's validator
    list, keyed by how many checks have already run -- each validator node adds exactly
    one key to `verification_report`, so its length is the index of the next step.
    `workspace_path` lets EDIT_REVIEW's F8 fallback (no prior report -> run FULL instead)
    resolve consistently across every step in the same run."""
    strategy = resolve_strategy(state.get("verification_strategy"), state.get("workspace_path"))
    completed = len(state["verification_report"])
    if completed >= len(strategy):
        return "finalize_report"
    return strategy[completed].node_name


def _finalize_report_node(state: VerificationState) -> dict:
    report = build_verification_report_for_checks(state["verification_report"])
    updates: dict[str, Any] = {"verification_report": report}
    ragas = report.get("ragas")
    if ragas is not None:
        updates["faithfulness_score"] = ragas["faithfulness_score"]
    return updates


def _write_artifacts_node(state: VerificationState) -> dict:
    ragas = state["verification_report"].get("ragas")
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
    for step in ALL_VALIDATOR_STEPS:
        graph.add_node(step.node_name, _make_validator_node(step))
    graph.add_node("finalize_report", _finalize_report_node)
    graph.add_node("write_artifacts", _write_artifacts_node)

    graph.add_edge(START, "load_context")
    all_targets = {step.node_name: step.node_name for step in ALL_VALIDATOR_STEPS}
    graph.add_conditional_edges("load_context", _route_after_load_context, all_targets)
    for step in ALL_VALIDATOR_STEPS:
        graph.add_conditional_edges(
            step.node_name,
            _route_after_validator,
            {**all_targets, "finalize_report": "finalize_report"},
        )
    graph.add_edge("finalize_report", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    return graph.compile()


@lru_cache
def get_verification_subgraph() -> CompiledStateGraph:
    return build_verification_subgraph()


def _resolve_verification_strategy(state: OrchestrationState) -> str:
    execution_plan = state.get("execution_plan")
    if not execution_plan:
        return "FULL"
    return RunExecutionPlan.model_validate(execution_plan).verification_strategy


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
        verification_strategy=_resolve_verification_strategy(state),
    )


def invoke_verification_subgraph(state: OrchestrationState) -> dict:
    """Run the Verification subgraph and map results back to orchestration updates."""
    result = get_verification_subgraph().invoke(to_verification_state(state))
    report = result["verification_report"]
    steps = ["load_context"]
    steps.extend(
        step.node_name
        for step in resolve_strategy(
            result.get("verification_strategy"), result.get("workspace_path")
        )
    )
    steps.extend(["finalize_report", "write_artifacts"])
    return merge_subgraph_updates(
        state,
        {
            "current_node": "verification",
            "verification_passed": report["passed"],
            "faithfulness_score": result["faithfulness_score"],
        },
        subgraph="verification",
        steps=steps,
    )


class VerificationGraph:
    """LangGraph graph for Verification subgraph."""

    def __init__(self) -> None:
        self._graph = get_verification_subgraph()

    def invoke(self, state: VerificationState) -> VerificationState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_verification_subgraph(state)
