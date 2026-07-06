from typing import Any

import pytest

from core.subgraphs.fitness.planner import (
    build_planner_payload,
    configure_fitness_planner,
    generate_structured_workout,
)
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.research.schema import ResearchFindings
from tests.helpers.fitness import default_structured_workout


@pytest.fixture(autouse=True)
def reset_fitness_planner_override() -> None:
    configure_fitness_planner(None)
    yield
    configure_fitness_planner(None)


@pytest.fixture
def sample_execution_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale="Research-backed fat loss plan with strength emphasis.",
        tasks=[
            PlanTask(
                order=1,
                task="Research evidence-based fat loss training volume",
                rationale="Volume must align with evidence for sustainable fat loss.",
            ),
            PlanTask(
                order=2,
                task="Gather equipment-specific exercise substitutions",
                rationale="User constraints require practical exercise swaps.",
            ),
            PlanTask(
                order=3,
                task="Verify source credibility for training recommendations",
                rationale="Downstream synthesis must rely on trustworthy evidence.",
            ),
        ],
        plan_markdown="# Plan\n\nFat loss with gym equipment and 3 training days per week.\n",
    )


@pytest.fixture
def sample_findings() -> ResearchFindings:
    return ResearchFindings(
        consensus="10-20 weekly sets per muscle group supports hypertrophy during fat loss phases.",
        key_findings=[
            "Full-body or upper/lower splits work well for 3-day schedules.",
            "Avoid overhead pressing with shoulder pain.",
        ],
        limitations=["Limited sport-specific data"],
        conflicting_evidence=[],
        recommended_sources=["https://example.com/hypertrophy"],
    )


def test_build_planner_payload_includes_feedback_and_findings(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    payload = build_planner_payload(
        profile={"goal": "fat_loss"},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        planner_feedback=["training_day_count_mismatch:expected_3_got_4"],
        verification_feedback="Increase weekly volume slightly.",
    )
    assert payload["execution_plan"]["plan_rationale"]
    assert "plan_markdown" not in payload["execution_plan"]
    assert "constraints" not in payload
    assert payload["structured_findings"]["consensus"]
    assert payload["planner_feedback"] == ["training_day_count_mismatch:expected_3_got_4"]
    assert payload["verification_feedback"] == "Increase weekly volume slightly."


def test_generate_structured_workout_uses_override(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    captured: dict[str, Any] = {}

    def override(**kwargs: Any):
        captured.update(kwargs)
        return default_structured_workout(kwargs["profile"], kwargs["constraints"])

    configure_fitness_planner(override)
    workout = generate_structured_workout(
        profile={"goal": "fat_loss", "days_per_week": 3},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        planner_feedback=[],
        verification_feedback=None,
    )
    assert workout.split == "3-day"
    assert len(workout.days) == 3
    assert captured["structured_findings"] == sample_findings
