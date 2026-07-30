"""Regression tests for the missing_structured_workout / verify_plan bug family.

Covers: (1) Supervisor capturing a pasted-into-chat plan as submitted_plan_text so
verify_plan never has to fail for lack of text, (2) the VFS fallback read in the
Fitness executor, (3) the LLM qualitative-review fallback for genuinely unparseable
text (that the internal `missing_structured_workout` diagnostic never leaks into a
user-facing summary), (4) normalize_submitted_plan correcting the extraction LLM's
unreliable self-reported weekly_sets total, and (5) humanize_safety_feedback keeping
raw safety codes out of anything user-facing. The verify_plan happy-path/unparseable
executor coverage duplicated with tests/test_fitness_executor_supervisor_routed.py
was removed from here rather than kept twice (see rule.md: no duplicate logic).
"""

from pathlib import Path
from typing import Any

import pytest

from core.agents.execution_context import ExecutionContext, build_execution_context
from core.agents.macro_report_judge import ReportedMacros, configure_reported_macros_judge
from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.subgraphs.fitness.executor import SupervisorRoutedFitnessExecutor
from core.subgraphs.fitness.normalize import (
    SubmittedPlanExtraction,
    SubmittedPlanQualitativeReview,
    SubmittedPlanVerificationReview,
    configure_qualitative_reviewer,
    configure_submitted_plan_extractor,
    configure_verification_explainer,
    normalize_submitted_plan,
    qualitative_review_unparseable_plan,
)
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.subgraphs.fitness.utils import humanize_safety_feedback
from core.vfs import VFS
from core.vfs.layout import PLAN_SUBMITTED_TEXT
from tests.helpers.fitness import default_structured_workout


@pytest.fixture(autouse=True)
def reset_submitted_plan_extractor():
    yield
    configure_submitted_plan_extractor(None)


@pytest.fixture(autouse=True)
def reset_qualitative_reviewer():
    yield
    configure_qualitative_reviewer(None)


@pytest.fixture(autouse=True)
def reset_verification_explainer():
    yield
    configure_verification_explainer(None)


@pytest.fixture(autouse=True)
def default_reported_macros_judge():
    """The unified verification path always consults the macro judge alongside the workout
    extractor -- default it to "nothing stated" for this file's plain workout-only fixtures
    so they don't hit the real LLM. Tests that care about macro numbers configure their own
    override, same pattern as the other judges in this file."""
    configure_reported_macros_judge(lambda _text: ReportedMacros())
    yield
    configure_reported_macros_judge(None)


def _stub_explainer_capturing(contexts: list[str], response: str):
    def _stub(context: str) -> SubmittedPlanVerificationReview:
        contexts.append(context)
        return SubmittedPlanVerificationReview(explanation=response)

    return _stub


def _verify_plan_state(
    workspace_root: Path,
    complete_profile: dict[str, Any],
    *,
    submitted_plan_text: str | None,
) -> tuple[OrchestrationState, ExecutionContext]:
    state = create_initial_state(
        run_id="verify-run",
        thread_id="verify-thread",
        query="Here's my plan, can you check it?",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
        submitted_plan_text=submitted_plan_text,
    )
    ctx = build_execution_context(
        intent="verify_plan", has_submitted_plan=bool(submitted_plan_text)
    )
    return state, ctx


def test_qualitative_review_skips_llm_call_for_empty_text():
    configure_submitted_plan_extractor(lambda _text: pytest.fail("should not be called"))
    configure_qualitative_reviewer(lambda _text: pytest.fail("should not be called"))
    review = qualitative_review_unparseable_plan("")
    assert "missing_structured_workout" not in review
    assert review


def test_qualitative_review_uses_override_and_never_leaks_internal_code():
    configure_qualitative_reviewer(
        lambda _text: SubmittedPlanQualitativeReview(
            review="I couldn't find any training days in that text -- can you resend it?"
        )
    )
    review = qualitative_review_unparseable_plan("some garbled non-workout text")
    assert review == "I couldn't find any training days in that text -- can you resend it?"
    assert "missing_structured_workout" not in review


def test_normalize_submitted_plan_recomputes_weekly_sets_instead_of_trusting_extractor():
    """Regression: the extraction LLM's self-reported `weekly_sets` total is unreliable
    (it's asked to sum sets across every exercise/day, and drifts) even when every
    individual exercise's sets were transcribed correctly -- exactly like generation mode
    (template_registry.py, planner.py), which never trusts that field either and always
    recomputes it. Left unrecomputed, this produced a spurious
    weekly_sets_mismatch:declared_58_computed_61 safety failure on a plan whose per-exercise
    sets were extracted correctly."""
    workout = StructuredWorkout(
        split="upper/lower",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name="Day 1",
                focus="Upper",
                exercises=[
                    WorkoutExercise(name="Bench Press", sets=4, reps="6-8"),
                    WorkoutExercise(name="Row", sets=4, reps="8-10"),
                ],
            ),
            WorkoutDay(
                name="Day 2",
                focus="Lower",
                exercises=[
                    WorkoutExercise(name="Squat", sets=4, reps="5-8"),
                    WorkoutExercise(name="RDL", sets=3, reps="6-10"),
                ],
            ),
        ],
        weekly_sets=58,  # deliberately wrong -- the actual sum below is 15
    )
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )

    result = normalize_submitted_plan("Day 1: Bench 4x6-8, Row 4x8-10...", {"days_per_week": 2})

    assert result["structured_workout"]["weekly_sets"] == 15


def test_verify_plan_does_not_fail_safety_check_on_extractor_weekly_sets_drift(
    workspace_root: Path, complete_profile: dict[str, Any]
):
    """End-to-end version of the regression above: even though the extractor declares the
    wrong weekly_sets, the corrected total means validate_plan's weekly_sets_mismatch check
    never fires and the plan passes."""
    state, ctx = _verify_plan_state(
        workspace_root,
        complete_profile,
        submitted_plan_text="Day 1: Bench 4x6-8, Row 4x8-10",
    )
    workout = StructuredWorkout(
        split="upper/lower",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name="Day 1",
                focus="Upper",
                exercises=[
                    WorkoutExercise(name="Bench Press", sets=4, reps="6-8"),
                    WorkoutExercise(name="Row", sets=4, reps="8-10"),
                ],
            )
        ]
        * 4,  # matches _verify_plan_state's days_per_week=4 constraint
        weekly_sets=999,  # deliberately wrong
    )
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    contexts: list[str] = []
    configure_verification_explainer(_stub_explainer_capturing(contexts, "Looks solid overall."))

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.summary == "Looks solid overall."
    assert result.artifacts["verification_passed"] is True
    # The explainer's input context reflects the corrected total, and the check passed --
    # no weekly_sets_mismatch finding was ever generated for it to see.
    assert "999" not in contexts[0]
    assert "weekly_sets_mismatch" not in contexts[0]
    assert "Deterministic safety check: PASSED" in contexts[0]


def test_humanize_safety_feedback_translates_codes_to_plain_english():
    readable = humanize_safety_feedback(
        [
            "training_day_count_mismatch:expected_4_got_2",
            "invalid_set_count:Bench Press:12",
            "duplicate_exercise:Day 1:squat",
            "aggressive_calorie_deficit",
        ]
    )
    assert len(readable) == 4
    joined = " | ".join(readable)
    # No raw codes/underscored-tokens leak through -- every entry reads as a sentence.
    assert "training_day_count_mismatch" not in joined
    assert "invalid_set_count" not in joined
    assert "2 training day(s)" in joined or "2 day(s)" in joined
    assert "Bench Press" in joined
    assert "squat" in joined.lower()


def test_verify_plan_failing_safety_check_still_gets_a_plain_english_explanation(
    workspace_root: Path, complete_profile: dict[str, Any]
):
    """A plan that fails the deterministic safety check also gets routed through
    explain_verified_plan (verification_passed=False), with humanized findings in its
    context -- not the old raw "; ".join(feedback) codes as the summary."""
    state, ctx = _verify_plan_state(
        workspace_root, complete_profile, submitted_plan_text="Day 1: Squat 3x5"
    )
    # Only 1 day, but _verify_plan_state's constraints expect days_per_week=4 ->
    # training_day_count_mismatch.
    workout = default_structured_workout(complete_profile, {"days_per_week": 1})
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    contexts: list[str] = []
    configure_verification_explainer(
        _stub_explainer_capturing(contexts, "This plan is missing 3 of your usual 4 training days.")
    )

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.artifacts["verification_passed"] is False
    assert result.summary == "This plan is missing 3 of your usual 4 training days."
    assert "training_day_count_mismatch" not in contexts[0]
    assert "Deterministic safety check: FAILED" in contexts[0]


def test_verify_plan_falls_back_to_vfs_when_state_submitted_plan_text_is_empty(
    workspace_root: Path, complete_profile: dict[str, Any]
):
    """Guards the VFS fallback read: even if the state snapshot's own submitted_plan_text
    field is empty (an older checkpoint, a resume path that didn't thread it through), the
    durable VFS copy written at Supervisor/create-run time is still used."""
    state, ctx = _verify_plan_state(workspace_root, complete_profile, submitted_plan_text=None)
    VFS.for_run(Path(state["workspace_path"])).write(PLAN_SUBMITTED_TEXT, "Day 1: Squat 3x5")

    workout = default_structured_workout(complete_profile, {"days_per_week": 4})
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    configure_verification_explainer(_stub_explainer_capturing([], "Explanation via VFS fallback."))

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.summary == "Explanation via VFS fallback."
    assert result.artifacts["verification_passed"] is True
