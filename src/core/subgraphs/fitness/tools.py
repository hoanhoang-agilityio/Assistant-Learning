from langchain_core.tools import BaseTool, tool


@tool
def calculate_macros(profile: dict, constraints: dict) -> dict:
    """Calculate calorie and macro targets from profile and constraints."""
    ...


@tool
def build_training_plan(
    profile: dict,
    macro_targets: dict,
    training_constraints: dict,
    evidence_summary: str | None,
) -> dict:
    """Build structured training plan from profile, macros, and evidence."""
    ...


@tool
def synthesize_plan(
    macro_targets: dict,
    training_plan: dict,
    evidence_summary: str | None,
    verification_feedback: str | None,
) -> dict:
    """Synthesize draft fitness plan markdown from macros and training plan."""
    ...


FITNESS_TOOLS: list[BaseTool] = [
    calculate_macros,
    build_training_plan,
    synthesize_plan,
]
