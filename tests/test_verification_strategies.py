from pathlib import Path
from typing import Any

import pytest

from core.graph.run import create_initial_state
from core.subgraphs.fitness.graph import build_fitness_subgraph, to_fitness_state
from core.subgraphs.fitness.normalize import (
    SubmittedPlanExtraction,
    configure_submitted_plan_extractor,
)
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.subgraphs.verification.graph import build_verification_subgraph, to_verification_state
from core.subgraphs.verification.strategies import (
    ALL_VALIDATOR_STEPS,
    CITATION,
    CONSISTENCY,
    FAITHFULNESS,
    SAFETY,
    VERIFICATION_STRATEGIES,
    resolve_strategy,
)
from core.subgraphs.verification.utils import (
    build_verification_report,
    build_verification_report_for_checks,
)
from tests.helpers.planning import seed_execution_plan


def test_full_strategy_runs_all_four_checks_in_order() -> None:
    assert VERIFICATION_STRATEGIES["FULL"] == [CITATION, CONSISTENCY, SAFETY, FAITHFULNESS]


def test_external_plan_strategy_never_includes_citation_or_faithfulness() -> None:
    strategy = VERIFICATION_STRATEGIES["EXTERNAL_PLAN"]
    assert strategy == [CONSISTENCY, SAFETY]
    assert CITATION not in strategy
    assert FAITHFULNESS not in strategy


def test_resolve_strategy_defaults_to_full_for_none_or_unset() -> None:
    assert resolve_strategy(None) == VERIFICATION_STRATEGIES["FULL"]


def test_all_validator_steps_covers_every_registered_step() -> None:
    registered = {step for strategy in VERIFICATION_STRATEGIES.values() for step in strategy}
    assert registered <= set(ALL_VALIDATOR_STEPS)


# --- Report aggregation ------------------------------------------------------------------


def _passing_check() -> dict:
    return {"passed": True, "issues": []}


def _failing_check(issue: str) -> dict:
    return {"passed": False, "issues": [issue]}


def _ragas(*, pass_fail: bool, score: float = 0.5) -> dict:
    return {
        "pass_fail": pass_fail,
        "faithfulness_score": score,
        "method": "heuristic",
        "threshold": 0.9,
    }


def test_build_verification_report_for_checks_matches_original_for_full_strategy() -> None:
    """The strategy-aware aggregator must be byte-identical to the original
    fixed-signature build_verification_report for the FULL case (design review, Phase 5
    backward-compat requirement)."""
    citation = _passing_check()
    consistency = _failing_check("missing_macro_targets")
    safety = _passing_check()
    ragas = _ragas(pass_fail=False, score=0.5)

    original = build_verification_report(
        citation=citation, consistency=consistency, safety=safety, ragas=ragas
    )
    via_checks = build_verification_report_for_checks(
        {"citation": citation, "consistency": consistency, "safety": safety, "ragas": ragas}
    )
    assert original == via_checks


def test_build_verification_report_for_checks_aggregates_only_present_checks() -> None:
    """EXTERNAL_PLAN: only consistency/safety present -- citation/ragas absence must never
    be treated as a failure."""
    consistency = _passing_check()
    safety = _passing_check()
    report = build_verification_report_for_checks({"consistency": consistency, "safety": safety})
    assert report["passed"] is True
    assert report["feedback"] is None
    assert "citation" not in report
    assert "ragas" not in report


def test_build_verification_report_for_checks_fails_on_present_check_failure() -> None:
    consistency = _failing_check("day_count_mismatch")
    safety = _passing_check()
    report = build_verification_report_for_checks({"consistency": consistency, "safety": safety})
    assert report["passed"] is False
    assert "Consistency issues" in report["feedback"]


# --- End-to-end: evaluate mode -> EXTERNAL_PLAN verification ---------------------------


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
        "days_per_week": 3,
    }


def test_external_plan_verification_runs_consistency_and_safety_only(
    tmp_path: Path, complete_profile: dict[str, Any]
) -> None:
    """Full pipeline: a submitted plan normalized by Fitness's evaluate mode, then
    verified under EXTERNAL_PLAN -- never touching citation/faithfulness, since no
    Research artifacts exist for a submitted plan."""
    orchestration_state = create_initial_state(
        run_id="external-plan-e2e",
        thread_id="external-plan-e2e-thread",
        query="check my plan",
        user_profile=complete_profile,
        workspace_root=tmp_path / "workspace",
        submitted_plan_text="Day 1: Squat 3x5\nDay 2: Bench 3x5\nDay 3: Deadlift 3x5",
    )
    seed_execution_plan(orchestration_state["workspace_path"], complete_profile)
    plan = {
        "user_intent": "verify",
        "workflow": "VerifyExternalWorkflow",
        "ordered_domains": ["fitness", "verify"],
        "fitness_mode": "evaluate",
        "verification_strategy": "EXTERNAL_PLAN",
    }
    orchestration_state = {**orchestration_state, "execution_plan": plan}

    workout = StructuredWorkout(
        split="3-day",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name=f"Day {i + 1}",
                focus="full body",
                exercises=[WorkoutExercise(name="Squat", sets=3, reps="5")],
            )
            for i in range(3)
        ],
        weekly_sets=9,
    )
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(parseable=True, workout=workout, findings=[])
    )
    fitness_result = build_fitness_subgraph().invoke(to_fitness_state(orchestration_state))
    configure_submitted_plan_extractor(None)
    assert fitness_result["structured_workout"] is not None

    verification_result = build_verification_subgraph().invoke(
        to_verification_state(orchestration_state)
    )
    report = verification_result["verification_report"]
    assert "citation" not in report
    assert "ragas" not in report
    assert "consistency" in report
    assert "safety" in report
    assert verification_result["faithfulness_score"] is None
