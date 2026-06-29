from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.tools import (
    build_training_plan,
    calculate_macros,
    synthesize_plan,
)
from core.subgraphs.fitness.utils import (
    detect_safety_flags_data,
    load_fitness_context,
    write_fitness_artifacts,
)


def _load_context_node(state: FitnessState) -> dict:
    context = load_fitness_context(state["workspace_path"])
    return {
        "profile": context["profile"] or state["profile"],
        "evidence_summary": context["evidence_summary"],
        "verification_feedback": context["verification_feedback"],
    }


def _calculate_macros_node(state: FitnessState) -> dict:
    return calculate_macros.invoke(
        {
            "profile": state["profile"],
            "constraints": state["constraints"],
        }
    )


def _build_training_plan_node(state: FitnessState) -> dict:
    return build_training_plan.invoke(
        {
            "profile": state["profile"],
            "macro_targets": state["macro_targets"],
            "training_constraints": state["training_constraints"],
            "evidence_summary": state["evidence_summary"],
        }
    )


def _safety_flags_node(state: FitnessState) -> dict:
    if state["training_plan"] is None:
        return {"safety_flags": ["missing_training_plan"]}
    return detect_safety_flags_data(
        profile=state["profile"],
        macro_targets=state["macro_targets"],
        training_plan=state["training_plan"],
    )


def _synthesize_plan_node(state: FitnessState) -> dict:
    if state["training_plan"] is None:
        return {"draft_plan": "# Fitness Plan Draft\n\nTraining plan unavailable.\n"}
    return synthesize_plan.invoke(
        {
            "macro_targets": state["macro_targets"],
            "training_plan": state["training_plan"],
            "evidence_summary": state["evidence_summary"],
            "verification_feedback": state["verification_feedback"],
            "safety_flags": state["safety_flags"],
        }
    )


def _write_artifacts_node(state: FitnessState) -> dict:
    if state["training_plan"] is None or state["draft_plan"] is None:
        return {}
    write_fitness_artifacts(
        workspace_path=state["workspace_path"],
        macro_targets=state["macro_targets"],
        training_plan=state["training_plan"],
        draft_plan=state["draft_plan"],
        safety_flags=state["safety_flags"],
    )
    return {}


def build_fitness_subgraph() -> CompiledStateGraph:
    """Compile the Fitness subgraph StateGraph."""
    graph = StateGraph(FitnessState)
    graph.add_node("load_context", _load_context_node)
    graph.add_node("calculate_macros", _calculate_macros_node)
    graph.add_node("build_training_plan", _build_training_plan_node)
    graph.add_node("safety_flags", _safety_flags_node)
    graph.add_node("synthesize_plan", _synthesize_plan_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "calculate_macros")
    graph.add_edge("calculate_macros", "build_training_plan")
    graph.add_edge("build_training_plan", "safety_flags")
    graph.add_edge("safety_flags", "synthesize_plan")
    graph.add_edge("synthesize_plan", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    return graph.compile()


@lru_cache
def get_fitness_subgraph() -> CompiledStateGraph:
    return build_fitness_subgraph()


def to_fitness_state(state: OrchestrationState) -> FitnessState:
    return FitnessState(
        workspace_path=state["workspace_path"],
        profile=state["user_profile"],
        constraints=state["constraints"],
        evidence_summary=None,
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        training_plan=None,
        draft_plan=None,
        safety_flags=[],
    )


def invoke_fitness_subgraph(state: OrchestrationState) -> dict:
    """Run the Fitness subgraph and map results back to orchestration updates."""
    get_fitness_subgraph().invoke(to_fitness_state(state))
    return {"current_node": "fitness"}


class FitnessGraph:
    """LangGraph graph for Fitness subgraph."""

    def __init__(self) -> None:
        self._graph = get_fitness_subgraph()

    def invoke(self, state: FitnessState) -> FitnessState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_fitness_subgraph(state)
