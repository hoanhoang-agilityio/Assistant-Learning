"""Unit tests for `SupervisorRoutedFitnessExecutor` -- the AgentResult-only Fitness
executor (status/blocking_reason/missing_information/summary/artifacts). See
tests/test_fitness_submitted_plan.py for the submitted-plan-specific regression
coverage (weekly_sets correction, VFS fallback, safety-feedback humanization) that
isn't duplicated here.
"""

from pathlib import Path
from typing import Any

from core.agents.execution_context import build_execution_context
from core.graph.run import create_initial_state
from core.subgraphs.fitness.executor import SupervisorRoutedFitnessExecutor
from core.subgraphs.fitness.normalize import (
    SubmittedPlanExtraction,
    SubmittedPlanQualitativeReview,
    SubmittedPlanVerificationReview,
    configure_qualitative_reviewer,
    configure_submitted_plan_extractor,
    configure_verification_explainer,
)
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

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.summary == "Looks solid overall."
    assert result.artifacts["verification_passed"] is True

    configure_submitted_plan_extractor(None)
    configure_verification_explainer(None)


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

    result = SupervisorRoutedFitnessExecutor().execute(state, ctx)

    assert result.summary == "No structured plan found here."
    assert result.artifacts["verification_passed"] is False
    assert "missing_structured_workout" not in result.summary

    configure_submitted_plan_extractor(None)
    configure_qualitative_reviewer(None)


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
