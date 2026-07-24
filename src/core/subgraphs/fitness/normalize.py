"""Normalization of a user-submitted plan into Fitness's `structured_workout` contract.

Phase 4 of the intent-aware orchestration refactor (see docs/reports/execution_plan_refactor/).
Kept separate from planner.py/template_registry.py: this module has no LLM-generation or
edit-classification concerns, only extraction of what the user already wrote.

Design review F2's constraint applies here too, in spirit: the extraction call is
instructed to transcribe only what the text actually states, never to invent missing
days/exercises or reconcile a mismatch with the profile -- that's the caller's job
(`normalize_submitted_plan`), recorded as a finding, never silently corrected.
"""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION
from core.subgraphs.fitness.schema import StructuredWorkout


class SubmittedPlanExtraction(BaseModel):
    """LLM verdict on whether a submitted plan's text contains a recognizable workout,
    and the workout itself if so.

    A separate wrapper type, not `StructuredWorkout` reused directly as the LLM call's own
    schema: a structured-output call otherwise has no way to say "nothing usable here" --
    `parseable=False` is that escape hatch. Forcing `StructuredWorkout` itself would risk
    the model fabricating a plausible-looking plan for genuinely unparseable input, which
    fails design-doc Sec5.4's "never coerce/fabricate" requirement.
    """

    parseable: bool = Field(
        description=(
            "False only if the text contains no recognizable training-day/exercise "
            "structure at all."
        )
    )
    workout: StructuredWorkout | None = Field(
        default=None,
        description="The extracted workout, present only when parseable is true.",
    )
    findings: list[str] = Field(
        default_factory=list,
        description=(
            "Notes about anything in the text that couldn't be confidently extracted -- "
            "e.g. a stated day count that doesn't match how many days were actually "
            "described, or explicit macro/calorie numbers mentioned in the text. Never "
            "used to justify inventing content; only to flag what's uncertain."
        ),
    )


SubmittedPlanExtractor = Callable[[str], SubmittedPlanExtraction]

_EXTRACTOR_OVERRIDE: SubmittedPlanExtractor | None = None

_EXTRACTION_SYSTEM_PROMPT = (
    """You transcribe a user's own written workout plan into a structured schema. You are
NOT designing a plan -- you are extracting exactly what is already written.

Rules:
- Extract only training days and exercises the text actually describes. Never invent a
  day, an exercise, or a set/rep count that isn't stated or clearly implied.
- If the text claims a day count (e.g. "my 4-day program") but only describes fewer days,
  extract only the days actually described and add a finding noting the gap. Do not
  fabricate the missing days.
- If you notice explicit calorie or macro numbers stated in the text, add a finding
  mentioning them -- do not use them to override anything else.
- If the text has no recognizable training-day/exercise structure at all, set
  parseable=false and leave workout unset. Do not force a guess.
- Reasonable defaults are fine only for fields the schema requires but the text is silent
  on and unambiguous from context (e.g. a day's "focus" label if only exercises are
  listed) -- never for the day count or exercise selection itself."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_submitted_plan_extractor(extractor: SubmittedPlanExtractor | None) -> None:
    """Override the submitted-plan extractor (used in tests)."""
    global _EXTRACTOR_OVERRIDE
    _EXTRACTOR_OVERRIDE = extractor


def extract_submitted_plan(submitted_plan_text: str) -> SubmittedPlanExtraction:
    """Ask the LLM to transcribe (not generate) a structured workout from submitted text."""
    if _EXTRACTOR_OVERRIDE is not None:
        return _EXTRACTOR_OVERRIDE(submitted_plan_text)
    token = set_llm_metrics_node("submitted_plan_extractor")
    try:
        return invoke_standard_structured_output(
            SubmittedPlanExtraction,
            [
                SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
                HumanMessage(content=submitted_plan_text),
            ],
            prompt_cache_key="submitted_plan_extractor",
        )
    finally:
        reset_llm_metrics_node(token)


def normalize_submitted_plan(
    submitted_plan_text: str,
    training_constraints: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a submitted plan into `structured_workout` + findings.

    Never reconciles a day-count/structure mismatch with `training_constraints` (profile-
    derived) -- the submitted plan's own shape is always preserved; a mismatch is recorded
    as a finding instead (design review F7, design-doc Sec5.4). Deliberately does not call
    `ensure_training_day_count`/`adapt_workout_to_blueprint` (unlike generate/edit modes):
    both would coerce the workout to match the profile-derived day count or scale set
    counts by a blueprint phase's volume modifier -- exactly the coercion this mode must
    not perform on a plan being verified as-submitted.

    Returns `{"structured_workout": None, "normalization_findings": [...]}` for
    unparseable input -- never raises; `_write_artifacts_node`'s existing
    `structured_workout is None` guard already handles that case with no new code there.
    """
    extraction = extract_submitted_plan(submitted_plan_text)
    findings = list(extraction.findings)

    if not extraction.parseable or extraction.workout is None:
        findings.append("unparseable: no recognizable training-day/exercise structure found")
        return {"structured_workout": None, "normalization_findings": findings}

    workout_dict = extraction.workout.model_dump()
    expected_days = int(training_constraints.get("days_per_week") or 0)
    actual_days = len(workout_dict.get("days", []))
    if expected_days and actual_days != expected_days:
        findings.append(
            f"day_count_mismatch: submitted plan has {actual_days} day(s), "
            f"profile expects {expected_days}"
        )

    return {"structured_workout": workout_dict, "normalization_findings": findings}
