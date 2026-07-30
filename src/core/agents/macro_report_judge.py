"""LLM judge that extracts the macro/calorie figures a user wants checked.

Only consulted for the verify_macros intent (core/subgraphs/fitness/executor.py) --
evaluate_macros needs to know what the user actually reported before it can
compare that against the recommended targets it computes from their profile.
Distinct from core/profile/extraction.py, which deliberately never infers
calorie/macro targets: this judge extracts the opposite thing, a number the
user stated about themselves, not a value the system should derive.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION


class ReportedMacros(BaseModel):
    """Macro/calorie figures the user stated about their own current or planned intake."""

    daily_calories: int | None = Field(
        default=None, description="Total daily calorie target the user reported, if any."
    )
    protein_g: int | None = Field(
        default=None, description="Daily protein in grams the user reported, if any."
    )
    carbs_g: int | None = Field(
        default=None, description="Daily carbohydrates in grams the user reported, if any."
    )
    fat_g: int | None = Field(
        default=None, description="Daily fat in grams the user reported, if any."
    )


MacroReportJudge = Callable[[str], ReportedMacros]

_JUDGE_SYSTEM_PROMPT = (
    """A user is asking whether their own daily macro/calorie numbers are
appropriate for their fitness goal. Extract only the figures they stated
about their own diet -- never compute, estimate, or infer a value yourself.
Leave a field null if that figure wasn't mentioned.

Examples:
"my macro per day is 3000" -> daily_calories=3000
"I'm eating 2200 kcal with 150g protein" -> daily_calories=2200, protein_g=150
"200g protein, 250g carbs, 70g fat" -> protein_g=200, carbs_g=250, fat_g=70
"is my diet ok?" -> all null"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def judge_reported_macros(query: str) -> ReportedMacros:
    token = set_llm_metrics_node("macro_report_judge")
    try:
        return invoke_standard_structured_output(
            ReportedMacros,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="macro_report_judge",
        )
    finally:
        reset_llm_metrics_node(token)
