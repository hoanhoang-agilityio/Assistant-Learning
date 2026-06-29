from langchain_core.tools import BaseTool, tool

from core.subgraphs.fitness.utils import (
    build_training_plan_data,
    calculate_macros_data,
    synthesize_plan_data,
)


@tool
def calculate_macros(profile: dict, constraints: dict) -> dict:
    """Calculate calorie and macro targets from profile and constraints."""
    return calculate_macros_data(profile, constraints)


@tool
def build_training_plan(
    profile: dict,
    macro_targets: dict,
    training_constraints: dict,
    evidence_summary: str | None,
) -> dict:
    """Build structured training plan from profile, macros, and evidence."""
    return build_training_plan_data(
        profile=profile,
        macro_targets=macro_targets,
        training_constraints=training_constraints,
        evidence_summary=evidence_summary,
    )


@tool
def synthesize_plan(
    macro_targets: dict,
    training_plan: dict,
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_flags: list[str],
) -> dict:
    """Synthesize draft fitness plan markdown from macros and training plan."""
    return synthesize_plan_data(
        macro_targets=macro_targets,
        training_plan=training_plan,
        evidence_summary=evidence_summary,
        verification_feedback=verification_feedback,
        safety_flags=safety_flags,
    )


FITNESS_TOOLS: list[BaseTool] = [
    calculate_macros,
    build_training_plan,
    synthesize_plan,
]
