from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.subgraphs.fitness.planner import generate_structured_workout
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.tools import calculate_macros, synthesize_plan
from core.subgraphs.fitness.utils import (
    default_execution_plan_for_fitness,
    load_fitness_context,
    load_prior_safety_feedback,
    validate_workout_safety_data,
    write_fitness_artifacts,
)
from core.subgraphs.research.schema import ResearchFindings


def _load_context_node(state: FitnessState) -> dict:
    context = load_fitness_context(state["workspace_path"])
    planner_feedback: list[str] = []
    if state["is_verification_rerun"]:
        planner_feedback = load_prior_safety_feedback(state["workspace_path"])
    return {
        "profile": context["profile"] or state["profile"],
        "execution_plan": context["execution_plan"],
        "structured_findings": context["structured_findings"],
        "evidence_summary": context["evidence_summary"],
        "verification_feedback": context["verification_feedback"],
        "planner_feedback": planner_feedback,
    }


def _calculate_macros_node(state: FitnessState) -> dict:
    return calculate_macros.invoke(
        {
            "profile": state["profile"],
            "constraints": state["constraints"],
        }
    )


def _fitness_planner_node(state: FitnessState) -> dict:
    execution_plan = default_execution_plan_for_fitness(state["execution_plan"])
    structured_findings = (
        ResearchFindings.model_validate(state["structured_findings"])
        if state["structured_findings"]
        else None
    )
    workout = generate_structured_workout(
        profile=state["profile"],
        constraints=state["constraints"],
        macro_targets=state["macro_targets"],
        training_constraints=state["training_constraints"],
        execution_plan=execution_plan,
        structured_findings=structured_findings,
        planner_feedback=state["planner_feedback"],
        verification_feedback=state["verification_feedback"],
    )
    return {
        "structured_workout": workout.model_dump(),
        "planner_attempts": state["planner_attempts"] + 1,
    }


def _safety_check_node(state: FitnessState) -> dict:
    safety_result = validate_workout_safety_data(
        profile=state["profile"],
        macro_targets=state["macro_targets"],
        training_constraints=state["training_constraints"],
        structured_workout=state["structured_workout"],
    )
    updates: dict = {"safety_result": safety_result}
    if not safety_result["passed"] and state["planner_attempts"] < state["max_planner_attempts"]:
        merged_feedback = list(state["planner_feedback"])
        for item in safety_result["feedback"]:
            if item not in merged_feedback:
                merged_feedback.append(item)
        updates["planner_feedback"] = merged_feedback
    return updates


def _route_after_safety(state: FitnessState) -> str:
    if state["safety_result"]["passed"]:
        return "synthesize_plan"
    if state["planner_attempts"] < state["max_planner_attempts"]:
        return "fitness_planner"
    return "synthesize_plan"


def _synthesize_plan_node(state: FitnessState) -> dict:
    return synthesize_plan.invoke(
        {
            "macro_targets": state["macro_targets"],
            "structured_workout": state["structured_workout"],
            "evidence_summary": state["evidence_summary"],
            "verification_feedback": state["verification_feedback"],
            "safety_result": state["safety_result"],
        }
    )


def _write_artifacts_node(state: FitnessState) -> dict:
    if state["structured_workout"] is None or state["draft_plan"] is None:
        return {}
    write_fitness_artifacts(
        workspace_path=state["workspace_path"],
        macro_targets=state["macro_targets"],
        structured_workout=state["structured_workout"],
        draft_plan=state["draft_plan"],
        safety_result=state["safety_result"],
    )
    return {}


def build_fitness_subgraph() -> CompiledStateGraph:
    """Compile the Fitness subgraph StateGraph."""
    graph = StateGraph(FitnessState)
    graph.add_node("load_context", _load_context_node)
    graph.add_node("calculate_macros", _calculate_macros_node)
    graph.add_node("fitness_planner", _fitness_planner_node)
    graph.add_node("safety_check", _safety_check_node)
    graph.add_node("synthesize_plan", _synthesize_plan_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "calculate_macros")
    graph.add_edge("calculate_macros", "fitness_planner")
    graph.add_edge("fitness_planner", "safety_check")
    graph.add_conditional_edges(
        "safety_check",
        _route_after_safety,
        {
            "fitness_planner": "fitness_planner",
            "synthesize_plan": "synthesize_plan",
        },
    )
    graph.add_edge("synthesize_plan", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    return graph.compile()


@lru_cache
def get_fitness_subgraph() -> CompiledStateGraph:
    return build_fitness_subgraph()


def resolve_max_planner_attempts(state: OrchestrationState) -> int:
    """Resolve planner retry budget for the current orchestration rerun context."""
    settings = get_settings()
    if state.get("route_decision") == "FIX_REASONING":
        return settings.fix_reasoning_planner_attempts
    return settings.max_planner_attempts


def to_fitness_state(state: OrchestrationState) -> FitnessState:
    is_verification_rerun = state.get("route_decision") == "FIX_REASONING"
    return FitnessState(
        workspace_path=state["workspace_path"],
        profile=state["user_profile"],
        constraints=state["constraints"],
        execution_plan={},
        structured_findings=None,
        evidence_summary=None,
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        structured_workout=None,
        safety_result={"passed": False, "feedback": []},
        planner_feedback=[],
        planner_attempts=0,
        max_planner_attempts=resolve_max_planner_attempts(state),
        is_verification_rerun=is_verification_rerun,
        draft_plan=None,
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
