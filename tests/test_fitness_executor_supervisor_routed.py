"""Unit tests for `SupervisorRoutedFitnessExecutor` -- the AgentResult-only Fitness
executor (status/blocking_reason/missing_information/summary/artifacts). See
tests/test_fitness_submitted_plan.py for the submitted-plan-specific regression
coverage (weekly_sets correction, VFS fallback, safety-feedback humanization) that
isn't duplicated here.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from core.capabilities.fitness import tools as fitness_tools
from core.capabilities.fitness.executor import SupervisorRoutedFitnessExecutor
from core.capabilities.fitness.normalize import (
    SubmittedPlanExtraction,
    SubmittedPlanQualitativeReview,
    SubmittedPlanVerificationReview,
    configure_qualitative_reviewer,
    configure_submitted_plan_extractor,
    configure_verification_explainer,
)
from core.orchestration.agents.macro_report_judge import (
    ReportedMacros,
    configure_reported_macros_judge,
)
from core.orchestration.graph.run import create_initial_state
from core.shared.execution_context import build_execution_context
from tests.helpers.fitness import default_structured_workout


def _verify_plan_state(
    workspace_root: Path, complete_profile: dict[str, Any], *, submitted_plan_text: str
):
    state = create_initial_state(
        run_id="verify-run-v2",
        thread_id="verify-thread-v2",
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


def test_build_plan_blocked_when_no_research_findings(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="build-run-v2",
        thread_id="build-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "blocked"
    assert result.blocking_reason == "Evidence needed for plan generation"
    assert result.missing_information == ["research_findings"]
    assert result.artifacts == {}


def test_build_plan_blocked_when_biometrics_missing(
    workspace_root: Path,
) -> None:
    """Regression: incomplete profile made calculate_macros return macro_targets=None,
    then render_plan crashed with TypeError: 'NoneType' object is not subscriptable."""
    import json

    from core.adapters.vfs import VFS

    state = create_initial_state(
        run_id="build-no-bio-v2",
        thread_id="build-no-bio-thread-v2",
        query="Build me a 4-day plan",
        user_profile={},
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    vfs = VFS.for_run(Path(state["workspace_path"]))
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "structured_findings": {
                    "consensus": "Resistance training supports fat loss outcomes for adults.",
                    "key_findings": [
                        {
                            "claim": "Train 3-4 days per week.",
                            "source_url": "https://example.edu/fitness-training",
                        }
                    ],
                    "limitations": [],
                    "recommended_sources": ["https://example.edu/fitness-training"],
                },
                "evidence": [
                    {
                        "url": "https://example.edu/fitness-training",
                        "content": "Train 3-4 days per week for fat loss.",
                    }
                ],
                "evidence_summary": "Train consistently.",
                "source_count": 1,
            }
        ),
    )
    ctx = build_execution_context(intent="build_plan")

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "blocked"
    assert result.missing_information == ["profile_biometrics"]
    assert "biometrics" in (result.blocking_reason or "").lower() or "Profile" in (
        result.blocking_reason or ""
    )


def test_after_verification_reports_completed_with_pass_verdict(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="after-verify-v2",
        thread_id="after-verify-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")
    state["last_capability_result"] = {
        "capability": "verification",
        "status": "completed",
        "artifacts": {"passed": True},
    }

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.artifacts == {"artifact_ready": True, "verification_passed": True}


def test_after_verification_carries_forward_failing_verdict(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="after-verify-fail-v2",
        thread_id="after-verify-fail-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")
    state["last_capability_result"] = {
        "capability": "verification",
        "status": "completed",
        "artifacts": {"passed": False},
    }

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    # Verification failing still reports "completed" (the fitness step itself didn't
    # fail) with verification_passed=False -- HITL always gets a chance to review,
    # never auto-blocked by a failed check (see policy_engine's HITL-before-persist
    # rule, which is the actual deterministic gate).
    assert result.status == "completed"
    assert result.artifacts["verification_passed"] is False


def test_verify_plan_happy_path_reports_summary_and_verification_passed(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state, ctx = _verify_plan_state(
        workspace_root, complete_profile, submitted_plan_text="Day 1: Squat 3x5\nDay 2: Bench 3x5"
    )
    workout = default_structured_workout(complete_profile, {"days_per_week": 4})
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    configure_verification_explainer(
        lambda _ctx: SubmittedPlanVerificationReview(explanation="Looks solid overall.")
    )
    configure_reported_macros_judge(lambda _text: ReportedMacros())

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.summary == "Looks solid overall."
    assert result.artifacts["verification_passed"] is True

    configure_submitted_plan_extractor(None)
    configure_verification_explainer(None)
    configure_reported_macros_judge(None)


def test_verify_plan_falls_back_to_qualitative_review_when_unparseable(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state, ctx = _verify_plan_state(
        workspace_root, complete_profile, submitted_plan_text="not a workout at all"
    )
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=False, workout=None, findings=[])
    )
    configure_qualitative_reviewer(
        lambda _text: SubmittedPlanQualitativeReview(review="No structured plan found here.")
    )
    configure_reported_macros_judge(lambda _text: ReportedMacros())

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.summary == "No structured plan found here."
    assert result.artifacts["verification_passed"] is False
    assert "missing_structured_workout" not in result.summary

    configure_submitted_plan_extractor(None)
    configure_qualitative_reviewer(None)
    configure_reported_macros_judge(None)


def test_verify_macros_intent_with_full_plan_also_verifies_the_workout(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """Regression: a full plan pasted alongside explicit macro numbers used to get
    classified verify_macros and silently lose the entire training review (see the
    conversation that prompted this fix). The Fitness capability now detects both the
    workout and the macro numbers regardless of which single intent the classifier
    picked, and merges them into one verification pass."""
    query = "Macro Targets: Calories: 2087 kcal, Protein: 131 g. Plus my 4-day split..."
    state = create_initial_state(
        run_id="verify-macros-with-plan",
        thread_id="verify-macros-with-plan-thread",
        query=query,
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
        submitted_plan_text=query,
    )
    ctx = build_execution_context(intent="verify_macros")
    workout = default_structured_workout(complete_profile, {"days_per_week": 4})
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    configure_reported_macros_judge(
        lambda _text: ReportedMacros(daily_calories=2087, protein_g=131)
    )
    contexts: list[str] = []

    def _capture(context: str):
        contexts.append(context)
        return SubmittedPlanVerificationReview(
            explanation="Training volume looks fine; calories are a bit low for the goal."
        )

    configure_verification_explainer(_capture)

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "completed"
    # Both halves ran: the deterministic workout safety check produced a pass/fail verdict
    # (proving validate_plan actually ran, not just the macro judge)...
    assert "verification_passed" in result.artifacts
    # ...and the macro comparison was folded into the same context/explanation instead of
    # being dropped because the classified intent was verify_macros.
    assert "Macro comparison" in contexts[0]
    assert "2087" in contexts[0]
    assert result.summary == "Training volume looks fine; calories are a bit low for the goal."

    configure_submitted_plan_extractor(None)
    configure_verification_explainer(None)
    configure_reported_macros_judge(None)


def test_revision_threads_days_per_week_explicit_into_select_template(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """A revision that explicitly named a new training frequency (User's
    apply_revision_overrides -- core.capabilities.user.utils -- sets
    `days_per_week_explicit=True` on state for exactly this) must reach
    select_template with that flag, so it skips the deterministic
    UPDATE_MACROS/REPLACE_EXERCISE shortcut (which never changes day count) and
    regenerates through the LLM edit path instead. Previously select_template
    hardcoded `days_per_week_explicit=False`, silently discarding this signal."""
    import json

    from core.adapters.vfs import VFS

    state = create_initial_state(
        run_id="revision-days-explicit",
        thread_id="revision-days-explicit-thread",
        query="change to 5 day training per week",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    VFS.for_run(Path(state["workspace_path"])).write(
        "research/findings.json",
        json.dumps(
            {
                "structured_findings": {
                    "consensus": "Resistance training supports fat loss outcomes for adults.",
                    "key_findings": [],
                    "limitations": [],
                    "recommended_sources": [],
                },
                "evidence": [],
                "evidence_summary": "Train consistently.",
                "source_count": 0,
            }
        ),
    )
    state["approval_status"] = "revision_requested"
    state["days_per_week_explicit"] = True
    ctx = build_execution_context(intent="build_plan")

    with patch.object(fitness_tools, "select_template", wraps=fitness_tools.select_template) as spy:
        SupervisorRoutedFitnessExecutor().execute(state, ctx)

    spy.assert_called_once()
    assert spy.call_args.kwargs["days_per_week_explicit"] is True


def test_calculate_calories_reports_summary(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="calc-run-v2",
        thread_id="calc-thread-v2",
        query="Calculate my TDEE",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="calculate_calories")

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert "TDEE" in result.summary
    assert result.artifacts == {}
