"""Tests for shared LLM compact serializers."""

from core.llm.serializers import (
    compact_execution_plan_for_llm,
    compact_macro_targets_for_llm,
    compact_profile_for_llm,
)
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def test_compact_profile_for_llm_strips_query_and_metadata() -> None:
    profile = {
        "query": "lose weight",
        "missing_fields": ["age"],
        "goal": "fat_loss",
        "age": 30,
    }
    compact = compact_profile_for_llm(profile)
    assert "query" not in compact
    assert "missing_fields" not in compact
    assert compact["goal"] == "fat_loss"


def test_compact_execution_plan_for_llm_omits_markdown() -> None:
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
    compact = compact_execution_plan_for_llm(plan)
    assert "plan_markdown" not in compact
    assert compact["plan_rationale"] == _MIN_PLAN_RATIONALE
    assert len(compact["tasks"]) == 3


def test_compact_macro_targets_for_llm_omits_goal_metadata() -> None:
    macro_targets = {
        "bmr": 1700,
        "tdee": 2200,
        "calories": 2000,
        "protein_g": 160,
        "carbs_g": 200,
        "fat_g": 60,
        "goal": "fat_loss",
        "activity_level": "gym_3x_week",
    }
    compact = compact_macro_targets_for_llm(macro_targets)
    assert "goal" not in compact
    assert "activity_level" not in compact
    assert compact["calories"] == 2000
