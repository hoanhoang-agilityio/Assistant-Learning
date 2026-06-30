"""Unit tests for planning agent normalization and research question building."""

from core.subgraphs.planning.planning_agent import normalize_execution_plan
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.research.utils import build_research_questions

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def test_normalize_execution_plan_reindexes_orders() -> None:
    plan = ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(order=3, task="Third research task for testing", rationale="Third rationale"),
            PlanTask(order=1, task="First research task for testing", rationale="First rationale"),
            PlanTask(
                order=2,
                task="Second research task for testing",
                rationale="Second rationale",
            ),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )
    normalized = normalize_execution_plan(plan)
    assert [task.order for task in normalized.tasks] == [1, 2, 3]
    assert normalized.tasks[0].task.startswith("First")


def test_build_research_questions_includes_rationale() -> None:
    plan = ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(
                order=1,
                task="Research fat loss training volume",
                rationale="Volume must match 3x/week gym schedule",
            ),
            PlanTask(
                order=2,
                task="Research protein intake during fat loss",
                rationale="Protein supports lean mass retention while cutting",
            ),
            PlanTask(
                order=3,
                task="Verify credibility of selected fat loss sources",
                rationale="Downstream synthesis needs trustworthy evidence",
            ),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )
    questions = build_research_questions("lose weight", plan)
    assert len(questions) == 3
    assert "Research fat loss training volume" in questions[0]
    assert "Volume must match 3x/week gym schedule" in questions[0]
    assert "lose weight" in questions[0]
