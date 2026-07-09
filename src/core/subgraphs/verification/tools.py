from langchain_core.tools import BaseTool, tool

from core.subgraphs.verification.utils import (
    citation_check_data,
    consistency_check_data,
    ragas_faithfulness_data,
    safety_check_data,
)


@tool
def citation_check(draft_plan: str, sources: list[dict]) -> dict:
    """Verify citations in the fitness plan against research sources."""
    return citation_check_data(draft_plan, sources)


@tool
def consistency_check(
    draft_plan: str,
    macro_targets: dict,
    training_plan: dict,
    plan_blueprint: dict | None = None,
) -> dict:
    """Check internal consistency between macros, training plan, and draft."""
    return consistency_check_data(draft_plan, macro_targets, training_plan, plan_blueprint)


@tool
def safety_check(
    draft_plan: str,
    safety_flags: list[str],
) -> dict:
    """Flag unsafe training volume, macro targets, or constraint conflicts."""
    return safety_check_data(draft_plan, safety_flags)


@tool
def ragas_faithfulness(draft_plan: str, evidence: list[dict]) -> dict:
    """Run RAGAS faithfulness evaluation against retrieved evidence."""
    return ragas_faithfulness_data(draft_plan, evidence)


VERIFICATION_TOOLS: list[BaseTool] = [
    citation_check,
    consistency_check,
    safety_check,
    ragas_faithfulness,
]
