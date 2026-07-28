"""Payload contract validation tests for LLM nodes."""

import pytest

from core.llm.contracts import (
    OPTIMIZATION_ROI_RANKING,
    validate_fitness_planner_payload,
    validate_research_context_payload,
)
from core.planning.schema import ExecutionPlan, PlanTask
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.fitness.planner import build_planner_payload
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.research.utils import build_research_context_payload

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def test_research_payload_contract_forbids_plan_markdown() -> None:
    plan = ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(order=1, task="First research task for testing", rationale="First rationale"),
            PlanTask(
                order=2, task="Second research task for testing", rationale="Second rationale"
            ),
            PlanTask(order=3, task="Third research task for testing", rationale="Third rationale"),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )
    profile = {"goal": "fat_loss", "query": "Build a plan"}
    payload = build_research_context_payload(
        query="Build a plan",
        profile=profile,
        goal_spec=derive_goal_spec(profile),
        execution_plan=plan,
    )
    validate_research_context_payload(payload)
    assert "plan_markdown" not in payload


def test_fitness_planner_payload_contract_is_compact(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    payload = build_planner_payload(
        profile={"goal": "fat_loss", "query": "lose weight", "days_per_week": 3},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={
            "calories": 2200,
            "protein_g": 160,
            "goal": "fat_loss",
            "activity_level": "gym_3x_week",
        },
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        planner_feedback=[],
        verification_feedback=None,
    )
    validate_fitness_planner_payload(payload)
    assert "constraints" not in payload
    assert "plan_markdown" not in payload["execution_plan"]
    assert "query" not in payload["profile"]
    assert "goal" not in payload["macro_targets"]


@pytest.fixture
def sample_execution_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(order=1, task="First research task for testing", rationale="First rationale"),
            PlanTask(
                order=2, task="Second research task for testing", rationale="Second rationale"
            ),
            PlanTask(order=3, task="Third research task for testing", rationale="Third rationale"),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )


@pytest.fixture
def sample_findings() -> ResearchFindings:
    return ResearchFindings(
        consensus="Consensus statement with enough characters for validation.",
        key_findings=["Finding one with enough detail.", "Finding two with enough detail."],
        limitations=["Limited data"],
        conflicting_evidence=[],
        recommended_sources=["https://example.com"],
    )


def test_roi_ranking_excludes_high_risk_context_reduction() -> None:
    high_risk = [item for item in OPTIMIZATION_ROI_RANKING if item["risk"] == "high"]
    assert any("Research evidence" in item["optimization"] for item in high_risk)
