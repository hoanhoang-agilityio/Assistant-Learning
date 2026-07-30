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
from core.subgraphs.fitness.utils import compute_weekly_sets


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


class SubmittedPlanQualitativeReview(BaseModel):
    """LLM verdict used only when no structured workout could be extracted at all.

    A free-text fallback, not a substitute for the structured safety checks -- it exists so
    the internal `missing_structured_workout` diagnostic (see fitness/utils.py) never has to
    be shown to the user verbatim; this gives them something useful instead.
    """

    review: str = Field(
        description=(
            "A short (2-4 sentence), direct, friendly response: state plainly that no "
            "structured day-by-day workout was found in the text, comment briefly on "
            "anything fitness-related that was present, and ask for the plan in a "
            "day/exercise/sets/reps format. Never invent or imply a workout that isn't there."
        )
    )


QualitativeReviewer = Callable[[str], SubmittedPlanQualitativeReview]

_QUALITATIVE_REVIEWER_OVERRIDE: QualitativeReviewer | None = None

_QUALITATIVE_REVIEW_SYSTEM_PROMPT = (
    """The user submitted text asking you to check their workout plan, but it contains no
recognizable training-day/exercise structure. Respond directly to them: say plainly you
couldn't find a structured plan in what they sent, briefly note anything fitness-related
that was present (if any), and ask them to resend it with clear days, exercises, sets, and
reps. Do not fabricate a workout or imply one exists."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_qualitative_reviewer(reviewer: QualitativeReviewer | None) -> None:
    """Override the unparseable-plan qualitative reviewer (used in tests)."""
    global _QUALITATIVE_REVIEWER_OVERRIDE
    _QUALITATIVE_REVIEWER_OVERRIDE = reviewer


def qualitative_review_unparseable_plan(submitted_plan_text: str) -> str:
    """Produce a user-facing fallback message when `structured_workout` couldn't be extracted.

    Never raises and never returns the raw `missing_structured_workout` code -- that stays an
    internal diagnostic in `SafetyResult.feedback`. Skips the LLM call entirely for empty
    input, since there's nothing to review.
    """
    if not submitted_plan_text.strip():
        return (
            "I didn't receive any plan text to review. Please paste the workout you'd like checked."
        )
    if _QUALITATIVE_REVIEWER_OVERRIDE is not None:
        return _QUALITATIVE_REVIEWER_OVERRIDE(submitted_plan_text).review
    token = set_llm_metrics_node("submitted_plan_qualitative_reviewer")
    try:
        result = invoke_standard_structured_output(
            SubmittedPlanQualitativeReview,
            [
                SystemMessage(content=_QUALITATIVE_REVIEW_SYSTEM_PROMPT),
                HumanMessage(content=submitted_plan_text),
            ],
            prompt_cache_key="submitted_plan_qualitative_reviewer",
        )
        return result.review
    finally:
        reset_llm_metrics_node(token)


class SubmittedPlanVerificationReview(BaseModel):
    """LLM-authored natural-language explanation of a completed verify_plan safety check.

    Every fact handed to this call (goal, archetype, macro targets, computed weekly sets,
    the plain-English safety findings, the pass/fail verdict itself) is already trusted,
    deterministically-computed data -- this call's only job is synthesizing it into a
    user-facing explanation and adding qualitative commentary on whether the exercise
    selection/volume actually suit the goal, which no rule in validate_workout_safety_data
    checks (it only enforces safety bounds, not goal-appropriateness quality).
    """

    explanation: str = Field(
        description=(
            "A natural-language verification summary, 3-7 sentences, covering: (1) whether "
            "the plan overall suits the stated goal, (2) whether training volume and "
            "exercise selection are sufficient to support it, (3) whether sets/reps/"
            "frequency are appropriate, (4) if there are weaknesses (from the given safety "
            "findings or your own read of the exercise selection), name them with a "
            "concrete, actionable suggestion, and (5) if a 'Macro comparison' line is given "
            "in the context, address whether the stated macros/calories also suit the goal "
            "(don't skip this just because the rest of the plan looks fine). Never "
            "contradict the given pass/fail verdict, safety findings, or macro comparison "
            "verdict, and never invent numbers not present in the input."
        )
    )


VerificationExplainer = Callable[[str], SubmittedPlanVerificationReview]

_VERIFICATION_EXPLAINER_OVERRIDE: VerificationExplainer | None = None

_VERIFICATION_EXPLANATION_SYSTEM_PROMPT = (
    """You explain the result of checking a user's submitted workout plan against their
fitness goal. You are given already-verified facts: the goal, the plan's structure (days,
exercises, sets, reps), macro targets if available, and the deterministic safety check's
pass/fail verdict plus any findings. Write a natural, direct explanation covering whether
the plan suits the goal, whether volume and exercise selection support it, whether
sets/reps/frequency look appropriate, and any weaknesses with a concrete suggested fix. If
a "Macro comparison" line is present in the context, also address whether the stated
macros/calories suit the goal -- this is not optional just because the training side looks
fine; the user asked about the whole plan. Ground everything in the given facts -- never
contradict the verdict/findings/macro comparison, never invent numbers, never claim a
problem the findings don't support."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_verification_explainer(explainer: VerificationExplainer | None) -> None:
    """Override the verified-plan explanation LLM call (used in tests)."""
    global _VERIFICATION_EXPLAINER_OVERRIDE
    _VERIFICATION_EXPLAINER_OVERRIDE = explainer


def explain_verified_plan(context: str) -> str:
    """Turn a verify_plan safety-check result into a user-facing natural-language summary.

    `context` is a pre-formatted, plain-text digest of trusted facts (see
    fitness/tools.py:explain_verified_plan) -- this call only synthesizes/explains them, it
    never recomputes or second-guesses the pass/fail verdict itself.
    """
    if _VERIFICATION_EXPLAINER_OVERRIDE is not None:
        return _VERIFICATION_EXPLAINER_OVERRIDE(context).explanation
    token = set_llm_metrics_node("submitted_plan_verification_explainer")
    try:
        result = invoke_standard_structured_output(
            SubmittedPlanVerificationReview,
            [
                SystemMessage(content=_VERIFICATION_EXPLANATION_SYSTEM_PROMPT),
                HumanMessage(content=context),
            ],
            prompt_cache_key="submitted_plan_verification_explainer",
        )
        return result.explanation
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
    # The extraction LLM is asked to transcribe weekly_sets as a sum, but -- like the
    # generation-mode LLM (see template_registry.py/planner.py, which never trust it either
    # and always recompute) -- it's unreliable at that arithmetic even when every individual
    # exercise's sets were transcribed correctly. This isn't content the "preserve the
    # submitted shape" rule (see docstring) protects: it's a redundant summary already fully
    # determined by `days`, so it's corrected here rather than surfaced as a spurious
    # weekly_sets_mismatch safety failure.
    workout_dict["weekly_sets"] = compute_weekly_sets(workout_dict)
    expected_days = int(training_constraints.get("days_per_week") or 0)
    actual_days = len(workout_dict.get("days", []))
    if expected_days and actual_days != expected_days:
        findings.append(
            f"day_count_mismatch: submitted plan has {actual_days} day(s), "
            f"profile expects {expected_days}"
        )

    return {"structured_workout": workout_dict, "normalization_findings": findings}
