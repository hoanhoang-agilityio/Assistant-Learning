"""LLM structured workout generation for the Fitness subgraph."""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.contracts import validate_fitness_planner_payload
from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import set_llm_metrics_node
from core.llm.payload import compact_json, limit_feedback_items
from core.llm.serializers import (
    compact_execution_plan_for_llm,
    compact_macro_targets_for_llm,
    compact_profile_for_llm,
)
from core.subgraphs.fitness.prompts import FITNESS_PLANNER_SYSTEM_PROMPT
from core.subgraphs.fitness.schema import StructuredWorkout
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.research.schema import ResearchFindings

PlannerOverride = Callable[..., StructuredWorkout]

_AGENT_OVERRIDE: PlannerOverride | None = None


def configure_fitness_planner(override: PlannerOverride | None) -> None:
    """Override the fitness planner (used in tests)."""
    global _AGENT_OVERRIDE
    _AGENT_OVERRIDE = override


def compact_structured_findings(
    structured_findings: ResearchFindings | None,
) -> dict[str, Any] | None:
    """Return a compact findings payload for the fitness planner."""
    if structured_findings is None:
        return None
    return {
        "consensus": structured_findings.consensus,
        "key_findings": structured_findings.key_findings[:3],
        "limitations": structured_findings.limitations[:2],
    }


def build_planner_payload(
    *,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    execution_plan: ExecutionPlan,
    structured_findings: ResearchFindings | None,
    planner_feedback: list[str],
    verification_feedback: str | None,
) -> dict[str, Any]:
    """Build the human-message payload sent to the fitness planner."""
    del constraints
    payload = {
        "profile": compact_profile_for_llm(profile),
        "macro_targets": compact_macro_targets_for_llm(macro_targets),
        "training_constraints": training_constraints,
        "execution_plan": compact_execution_plan_for_llm(execution_plan),
        "structured_findings": compact_structured_findings(structured_findings),
        "planner_feedback": limit_feedback_items(planner_feedback),
        "verification_feedback": verification_feedback,
    }
    validate_fitness_planner_payload(payload)
    return payload


def generate_structured_workout(
    *,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    execution_plan: ExecutionPlan,
    structured_findings: ResearchFindings | None,
    planner_feedback: list[str],
    verification_feedback: str | None,
) -> StructuredWorkout:
    """Generate a structured workout via LLM structured output."""
    if _AGENT_OVERRIDE is not None:
        return _AGENT_OVERRIDE(
            profile=profile,
            constraints=constraints,
            macro_targets=macro_targets,
            training_constraints=training_constraints,
            execution_plan=execution_plan,
            structured_findings=structured_findings,
            planner_feedback=planner_feedback,
            verification_feedback=verification_feedback,
        )
    payload = build_planner_payload(
        profile=profile,
        constraints=constraints,
        macro_targets=macro_targets,
        training_constraints=training_constraints,
        execution_plan=execution_plan,
        structured_findings=structured_findings,
        planner_feedback=planner_feedback,
        verification_feedback=verification_feedback,
    )
    token = set_llm_metrics_node("fitness_planner")
    try:
        return invoke_standard_structured_output(
            StructuredWorkout,
            [
                SystemMessage(content=FITNESS_PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=compact_json(payload)),
            ],
        )
    finally:
        from core.llm.metrics import reset_llm_metrics_node

        reset_llm_metrics_node(token)
