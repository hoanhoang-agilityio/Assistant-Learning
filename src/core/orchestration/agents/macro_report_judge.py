"""LLM judge that extracts the macro/calorie figures a user wants checked.

Consulted whenever a verification request (verify_macros or verify_plan --
core/subgraphs/fitness/executor.py) needs to know what daily calorie/macro
numbers the user actually wants evaluated, before comparing those against the
recommended targets computed from their profile. The figures can come from
either framing: the user's own reported current intake, or macro targets
written into a plan they pasted for review (a "Macro Targets" section, say) --
both are numbers already stated in the text, not values the system should
derive. Distinct from core/profile/extraction.py, which deliberately never
infers calorie/macro targets: this judge extracts numbers already present in
the text, never computes or estimates one itself.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.adapters.llm.factory import invoke_standard_structured_output
from core.adapters.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.adapters.llm.prompt_fragments import JSON_ONLY_INSTRUCTION


class ReportedMacros(BaseModel):
    """Macro/calorie figures stated in the text: the user's own current/planned
    intake, or the macro targets of a plan they submitted for review."""

    daily_calories: int | None = Field(
        default=None, description="Total daily calorie target stated in the text, if any."
    )
    protein_g: int | None = Field(
        default=None, description="Daily protein in grams stated in the text, if any."
    )
    carbs_g: int | None = Field(
        default=None, description="Daily carbohydrates in grams stated in the text, if any."
    )
    fat_g: int | None = Field(
        default=None, description="Daily fat in grams stated in the text, if any."
    )


MacroReportJudge = Callable[[str], ReportedMacros]

_JUDGE_OVERRIDE: MacroReportJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """Extract the daily macro/calorie figures stated in the text that the user
wants checked against their fitness goal. These can be framed either as the
user's own current/planned intake, or as the macro targets of a plan they
pasted in for review (e.g. a "Macro Targets" section listing calories/protein/
carbs/fat). Extract only figures actually stated -- never compute, estimate,
or infer a value yourself. Leave a field null if that figure wasn't mentioned.

Examples:
"my macro per day is 3000" -> daily_calories=3000
"I'm eating 2200 kcal with 150g protein" -> daily_calories=2200, protein_g=150
"200g protein, 250g carbs, 70g fat" -> protein_g=200, carbs_g=250, fat_g=70
"Macro Targets\\nCalories: 2087 kcal\\nProtein: 131 g\\nCarbs: 260 g\\nFat: 58 g" ->
    daily_calories=2087, protein_g=131, carbs_g=260, fat_g=58
"Here's my 4-day split: [workout only, no numbers]" -> all null
"is my diet ok?" -> all null"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_reported_macros_judge(judge: MacroReportJudge | None) -> None:
    """Override the reported-macros judge (used in tests)."""
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_reported_macros(query: str) -> ReportedMacros:
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(query)
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
