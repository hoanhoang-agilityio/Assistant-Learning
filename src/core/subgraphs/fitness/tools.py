from langchain_core.tools import BaseTool, tool

from core.subgraphs.fitness.utils import (
    calculate_macros_data,
    synthesize_plan_data,
)


@tool
def calculate_macros(profile: dict, constraints: dict) -> dict:
    """Calculate calorie and macro targets from profile and constraints."""
    return calculate_macros_data(profile, constraints)


@tool
def synthesize_plan(
    macro_targets: dict,
    structured_workout: dict | None,
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_result: dict,
) -> dict:
    """Synthesize draft fitness plan markdown from macros and structured workout."""
    return synthesize_plan_data(
        macro_targets=macro_targets,
        structured_workout=structured_workout,
        evidence_summary=evidence_summary,
        verification_feedback=verification_feedback,
        safety_result=safety_result,
    )


FITNESS_TOOLS: list[BaseTool] = [
    calculate_macros,
    synthesize_plan,
]
