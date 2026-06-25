from langchain_core.tools import BaseTool, tool


@tool
def citation_check(draft_plan: str, sources: list[dict]) -> dict:
    """Verify citations in the fitness plan against research sources."""
    ...


@tool
def consistency_check(
    draft_plan: str,
    macro_targets: dict,
    training_plan: dict,
) -> dict:
    """Check internal consistency between macros, training plan, and draft."""
    ...


@tool
def safety_check(draft_plan: str, profile: dict, constraints: dict) -> dict:
    """Flag unsafe training volume, macro targets, or constraint conflicts."""
    ...


@tool
def ragas_faithfulness(draft_plan: str, evidence: list[dict]) -> dict:
    """Run RAGAS faithfulness evaluation against retrieved evidence."""
    ...


VERIFICATION_TOOLS: list[BaseTool] = [
    citation_check,
    consistency_check,
    safety_check,
    ragas_faithfulness,
]
