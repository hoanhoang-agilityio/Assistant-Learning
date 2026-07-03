from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.research.utils import build_research_context_payload

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def test_build_research_context_payload_strips_query_from_profile() -> None:
    profile = {
        "query": "I want to lose weight with a gym 3x/week plan.",
        "age": 30,
        "goal": "fat_loss",
        "activity_level": "gym_3x_week",
    }
    payload = build_research_context_payload(
        query=profile["query"],
        request_type="fat_loss",
        profile=profile,
    )
    assert payload["query"] == profile["query"]
    assert "query" not in payload["profile"]
    assert payload["profile"]["goal"] == "fat_loss"
    assert payload["request_type"] == "fat_loss"


def test_build_research_context_payload_includes_execution_plan_fields() -> None:
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
    payload = build_research_context_payload(
        query="Build a plan",
        request_type=None,
        profile={"goal": "fat_loss"},
        execution_plan=plan,
        extra={"source_count": 2},
    )
    assert "request_type" not in payload
    assert payload["plan_rationale"] == _MIN_PLAN_RATIONALE
    assert len(payload["tasks"]) == 3
    assert payload["source_count"] == 2
