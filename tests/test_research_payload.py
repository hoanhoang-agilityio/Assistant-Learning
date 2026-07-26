from core.llm.serializers import compact_execution_plan_for_llm, compact_profile_for_llm
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.research.utils import (
    build_eval_llm_extra,
    build_research_context_payload,
    build_synthesis_llm_extra,
)

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def _sample_plan() -> ExecutionPlan:
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
        goal_spec=derive_goal_spec(profile),
    )
    assert payload["query"] == profile["query"]
    assert "query" not in payload["profile"]
    assert payload["profile"]["goal"] == "fat_loss"
    assert "request_type" not in payload


def test_build_research_context_payload_keeps_distinct_request_type() -> None:
    profile = {"goal": "fat_loss"}
    payload = build_research_context_payload(
        query="Build a training plan",
        request_type="training_plan",
        profile=profile,
        goal_spec=derive_goal_spec(profile),
    )
    assert payload["request_type"] == "training_plan"


def test_build_research_context_payload_includes_execution_plan_fields() -> None:
    plan = _sample_plan()
    profile = {"goal": "fat_loss"}
    payload = build_research_context_payload(
        query="Build a plan",
        request_type=None,
        profile=profile,
        goal_spec=derive_goal_spec(profile),
        execution_plan=plan,
        extra={"source_count": 2},
    )
    assert "request_type" not in payload
    assert payload["plan_rationale"] == _MIN_PLAN_RATIONALE
    assert len(payload["tasks"]) == 3
    assert payload["source_count"] == 2


def test_build_research_context_payload_react_omits_execution_plan() -> None:
    profile = {"goal": "fat_loss"}
    payload = build_research_context_payload(
        query="Build a plan",
        request_type="training_plan",
        profile=profile,
        goal_spec=derive_goal_spec(profile),
    )
    assert "plan_rationale" not in payload
    assert "tasks" not in payload


def test_compact_profile_drops_activity_level_when_days_per_week_present() -> None:
    profile = compact_profile_for_llm(
        {
            "goal": "fat_loss",
            "activity_level": "gym_3x_week",
            "days_per_week": 3,
        }
    )
    assert profile["days_per_week"] == 3
    assert "activity_level" not in profile


def test_compact_execution_plan_omits_task_rationale() -> None:
    plan = _sample_plan()
    compact = compact_execution_plan_for_llm(plan, include_task_rationale=False)
    assert compact["tasks"][0] == {"order": 1, "task": "First research task for testing"}
    assert "rationale" not in compact["tasks"][0]


def test_build_eval_llm_extra_compact_sources() -> None:
    sources = [
        {
            "source_id": "a",
            "title": "Study",
            "url": "https://pubmed.ncbi.nlm.nih.gov/study",
            "snippet": "x" * 300,
            "score": 0.9,
            "provider": "tavily",
            "research_query": "query",
        }
    ]
    evidence = [{"url": "https://pubmed.ncbi.nlm.nih.gov/study", "content": "Full text"}]
    extra = build_eval_llm_extra(sources, evidence)
    assert "source_count" not in extra
    assert extra["sources_preview"][0] == {
        "title": "Study",
        "url": "https://pubmed.ncbi.nlm.nih.gov/study",
        "snippet": "x" * 200,
    }
    assert extra["evidence_preview"][0]["content_preview"] == "Full text"


def test_build_synthesis_llm_extra_dedupes_urls() -> None:
    shared_url = "https://pubmed.ncbi.nlm.nih.gov/study"
    sources = [
        {
            "title": "Study",
            "url": shared_url,
            "snippet": "snippet",
            "rank": 1,
            "composite_score": 0.9,
        },
        {
            "title": "Other",
            "url": "https://example.com/other",
            "snippet": "other snippet",
            "rank": 2,
        },
    ]
    evidence = [{"url": shared_url, "content": "Full extracted content"}]
    extra = build_synthesis_llm_extra(sources, evidence)
    assert extra["evidence"] == [{"url": shared_url, "content": "Full extracted content"}]
    catalog_urls = [item["url"] for item in extra["source_catalog"]]
    assert shared_url not in catalog_urls
    assert "https://example.com/other" in catalog_urls
