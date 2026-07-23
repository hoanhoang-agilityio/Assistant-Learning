from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.subgraphs.fitness.blueprint import build_plan_blueprint
from core.subgraphs.fitness.planner import generate_structured_workout
from core.subgraphs.fitness.schema import EditOperation
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.template_registry import (
    adapt_workout_to_blueprint,
    resolve_workout_template,
    store_workout_template,
)
from core.subgraphs.fitness.utils import (
    calculate_macros_data,
    default_execution_plan_for_fitness,
    ensure_training_day_count,
    load_fitness_context,
    load_prior_safety_feedback,
    resolve_expected_day_count,
    synthesize_plan_data,
    validate_edit_result,
    validate_workout_safety_data,
    write_fitness_artifacts,
)
from core.subgraphs.planning.utils import load_revision_feedback
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.wrapper import merge_subgraph_updates


def _load_context_node(state: FitnessState) -> dict:
    context = load_fitness_context(state["workspace_path"])
    planner_feedback: list[str] = []
    if state["is_verification_rerun"]:
        planner_feedback = load_prior_safety_feedback(state["workspace_path"])
    return {
        "profile": context["profile"],
        "constraints": context["constraints"],
        "execution_plan": context["execution_plan"],
        "structured_findings": context["structured_findings"],
        "evidence_summary": context["evidence_summary"],
        "verification_feedback": context["verification_feedback"],
        "planner_feedback": planner_feedback,
    }


def _build_blueprint_node(state: FitnessState) -> dict:
    blueprint = build_plan_blueprint(state["profile"], state["constraints"])
    return {"plan_blueprint": blueprint.model_dump()}


def _calculate_macros_node(state: FitnessState) -> dict:
    return calculate_macros_data(state["profile"], state["constraints"])


def _resolve_workout_template_node(state: FitnessState) -> dict:
    from core.subgraphs.fitness.blueprint import PlanBlueprint

    blueprint = PlanBlueprint.model_validate(state["plan_blueprint"])
    resolution = resolve_workout_template(
        workspace_path=state["workspace_path"],
        profile=state["profile"],
        constraints=state["constraints"],
        blueprint=blueprint,
        planner_feedback=state["planner_feedback"],
        verification_feedback=state["verification_feedback"],
        is_verification_rerun=state["is_verification_rerun"],
        days_per_week_explicit=state.get("days_per_week_explicit", False),
    )
    updates: dict = {
        "template_fingerprint": resolution["template_fingerprint"],
        "workout_source": resolution["workout_source"],
        "reused_workout": resolution["reused_workout"],
    }
    if "edit_operation" in resolution:
        updates["edit_operation"] = resolution["edit_operation"]
        updates["previous_workout"] = resolution["previous_workout"]
    if resolution["structured_workout"] is not None:
        updates["structured_workout"] = adapt_workout_to_blueprint(
            resolution["structured_workout"],
            blueprint,
        )
    return updates


def _route_after_template_resolution(state: FitnessState) -> str:
    if state.get("structured_workout") is not None:
        return "safety_check"
    return "fitness_planner"


def _fitness_planner_node(state: FitnessState) -> dict:
    execution_plan = default_execution_plan_for_fitness(state["execution_plan"])
    structured_findings = (
        ResearchFindings.model_validate(state["structured_findings"])
        if state["structured_findings"]
        else None
    )
    revision_feedback = load_revision_feedback(state["workspace_path"])
    previous_workout = state.get("previous_workout")
    edit_operation_data = state.get("edit_operation")
    edit_operation = (
        EditOperation.model_validate(edit_operation_data) if edit_operation_data else None
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
        revision_feedback=revision_feedback,
        mode="edit" if edit_operation is not None else "generate",
        previous_workout=previous_workout,
        edit_operation=edit_operation,
    )

    # resolve_expected_day_count is the single source of truth for the target day
    # count -- during an edit it's normally derived from previous_workout (never from
    # the static profile-derived training_constraints), so it stays in agreement with
    # what _safety_check_node validates against below. The one exception is when this
    # revision explicitly named a new training frequency (days_per_week_explicit):
    # then training_constraints["days_per_week"] -- itself sourced from the freshly
    # revised profile -- wins over any edit-operation arithmetic.
    expected_days = resolve_expected_day_count(
        edit_operation,
        previous_workout,
        state["training_constraints"],
        days_per_week_explicit=state.get("days_per_week_explicit", False),
    )
    training_constraints = {**state["training_constraints"], "days_per_week": expected_days}

    workout = ensure_training_day_count(
        workout,
        training_constraints,
        state["profile"],
    )
    from core.subgraphs.fitness.blueprint import PlanBlueprint

    blueprint = PlanBlueprint.model_validate(state["plan_blueprint"])
    adapted = adapt_workout_to_blueprint(workout.model_dump(), blueprint)
    return {
        "structured_workout": adapted,
        "planner_attempts": state["planner_attempts"] + 1,
        "workout_source": "llm",
        "reused_workout": False,
    }


def _safety_check_node(state: FitnessState) -> dict:
    previous_workout = state.get("previous_workout")
    edit_operation_data = state.get("edit_operation")
    edit_operation = (
        EditOperation.model_validate(edit_operation_data) if edit_operation_data else None
    )

    # Same resolve_expected_day_count call, same inputs, as _fitness_planner_node
    # used to produce this candidate -- so the day-count check below can never
    # flag a correctly-edited plan as a "mismatch" against a stale
    # training_constraints["days_per_week"] the candidate was never targeting.
    expected_days = resolve_expected_day_count(
        edit_operation,
        previous_workout,
        state["training_constraints"],
        days_per_week_explicit=state.get("days_per_week_explicit", False),
    )
    training_constraints = {**state["training_constraints"], "days_per_week": expected_days}

    safety_result = validate_workout_safety_data(
        profile=state["profile"],
        macro_targets=state["macro_targets"],
        training_constraints=training_constraints,
        structured_workout=state["structured_workout"],
    )

    edit_issues: list[str] = []
    if edit_operation is not None and previous_workout is not None:
        edit_issues = validate_edit_result(
            edit_operation, previous_workout, state["structured_workout"]
        )
        if edit_issues:
            merged = sorted(set(safety_result["feedback"]) | set(edit_issues))
            safety_result = {"passed": False, "feedback": merged}

    updates: dict = {"safety_result": safety_result}
    if not safety_result["passed"]:
        if state["planner_attempts"] < state["max_planner_attempts"]:
            merged_feedback = list(state["planner_feedback"])
            for item in safety_result["feedback"]:
                if item not in merged_feedback:
                    merged_feedback.append(item)
            updates["planner_feedback"] = merged_feedback
            updates["structured_workout"] = None
            updates["reused_workout"] = False
        elif edit_issues:
            # Revert to the unchanged prior plan, and recompute safety_result
            # against THAT plan (not the discarded failed candidate) so
            # structured_workout, safety_result, the persisted artifacts, and
            # the rendered draft plan all describe the same workout.
            #
            # days_per_week is overridden to previous_workout's own actual day
            # count, not state["training_constraints"]["days_per_week"] -- that
            # field is a static, never-mutated profile default and can be stale
            # relative to a plan already edited in an earlier turn (e.g. a prior
            # successful ADD_DAY took it from 3 to 4 days). previous_workout's
            # own day count is definitionally correct here, regardless of which
            # operation was being attempted this turn, since we're reverting to
            # it exactly as it was.
            reverted_training_constraints = {
                **state["training_constraints"],
                "days_per_week": len(previous_workout.get("days", [])),
            }
            updates["safety_result"] = validate_workout_safety_data(
                profile=state["profile"],
                macro_targets=state["macro_targets"],
                training_constraints=reverted_training_constraints,
                structured_workout=previous_workout,
            )
            updates["structured_workout"] = previous_workout
            updates["edit_failed"] = True
    else:
        # Cache write gated on a passing safety check -- writing here (not in
        # _fitness_planner_node) ensures a plan that fails safety validation
        # can never poison TemplateRegistry, which is a cross-user read
        # surface keyed only on days/equipment/blueprint-family.
        fingerprint = state.get("template_fingerprint")
        if fingerprint and state.get("workout_source") == "llm":
            store_workout_template(fingerprint, state["structured_workout"], source="llm")
    return updates


def _route_after_safety(state: FitnessState) -> str:
    if state["safety_result"]["passed"]:
        return "synthesize_plan"
    if state["planner_attempts"] < state["max_planner_attempts"]:
        return "fitness_planner"
    return "synthesize_plan"


def _synthesize_plan_node(state: FitnessState) -> dict:
    return synthesize_plan_data(
        macro_targets=state["macro_targets"],
        structured_workout=state["structured_workout"],
        evidence_summary=state["evidence_summary"],
        verification_feedback=state["verification_feedback"],
        safety_result=state["safety_result"],
        plan_blueprint=state["plan_blueprint"],
        edit_failed=state.get("edit_failed", False),
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
        plan_blueprint=state["plan_blueprint"],
        template_fingerprint=state.get("template_fingerprint"),
        workout_source=state.get("workout_source"),
    )
    return {}


def build_fitness_subgraph() -> CompiledStateGraph:
    """Compile the Fitness subgraph StateGraph."""
    graph = StateGraph(FitnessState)
    graph.add_node("load_context", _load_context_node)
    graph.add_node("build_blueprint", _build_blueprint_node)
    graph.add_node("calculate_macros", _calculate_macros_node)
    graph.add_node("resolve_workout_template", _resolve_workout_template_node)
    graph.add_node("fitness_planner", _fitness_planner_node)
    graph.add_node("safety_check", _safety_check_node)
    graph.add_node("synthesize_plan", _synthesize_plan_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "build_blueprint")
    graph.add_edge("build_blueprint", "calculate_macros")
    graph.add_edge("calculate_macros", "resolve_workout_template")
    graph.add_conditional_edges(
        "resolve_workout_template",
        _route_after_template_resolution,
        {
            "safety_check": "safety_check",
            "fitness_planner": "fitness_planner",
        },
    )
    graph.add_edge("fitness_planner", "safety_check")
    graph.add_conditional_edges(
        "safety_check",
        _route_after_safety,
        {
            "resolve_workout_template": "resolve_workout_template",
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
        profile={},
        constraints={},
        days_per_week_explicit=state.get("days_per_week_explicit", False),
        execution_plan={},
        structured_findings=None,
        evidence_summary=None,
        verification_feedback=None,
        plan_blueprint={},
        macro_targets={},
        training_constraints={},
        structured_workout=None,
        safety_result={"passed": False, "feedback": []},
        planner_feedback=[],
        planner_attempts=0,
        max_planner_attempts=resolve_max_planner_attempts(state),
        is_verification_rerun=is_verification_rerun,
        draft_plan=None,
        template_fingerprint=None,
        workout_source=None,
        reused_workout=False,
        edit_operation=None,
        previous_workout=None,
        edit_failed=False,
    )


def invoke_fitness_subgraph(state: OrchestrationState) -> dict:
    """Run the Fitness subgraph and map results back to orchestration updates."""
    result = get_fitness_subgraph().invoke(to_fitness_state(state))
    steps = [
        "load_context",
        "build_blueprint",
        "calculate_macros",
        "resolve_workout_template",
    ]
    if result.get("reused_workout"):
        steps.append("reuse_workout_template")
    else:
        steps.append("fitness_planner")
    steps.append("safety_check")
    if int(result.get("planner_attempts") or 0) > 1:
        steps.append("fitness_planner_retry")
    steps.extend(["synthesize_plan", "write_artifacts"])
    return merge_subgraph_updates(
        state,
        {"current_node": "fitness"},
        subgraph="fitness",
        steps=steps,
    )


class FitnessGraph:
    """LangGraph graph for Fitness subgraph."""

    def __init__(self) -> None:
        self._graph = get_fitness_subgraph()

    def invoke(self, state: FitnessState) -> FitnessState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_fitness_subgraph(state)
