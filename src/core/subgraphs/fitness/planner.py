"""LLM structured workout generation for the Fitness subgraph."""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import invoke_standard_structured_output
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
    return {
        "profile": profile,
        "constraints": constraints,
        "macro_targets": macro_targets,
        "training_constraints": training_constraints,
        "execution_plan": execution_plan.model_dump(),
        "structured_findings": (
            structured_findings.model_dump() if structured_findings is not None else None
        ),
        "planner_feedback": planner_feedback,
        "verification_feedback": verification_feedback,
    }


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
    return invoke_standard_structured_output(
        StructuredWorkout,
        [
            SystemMessage(content=FITNESS_PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ],
    )
