"""Unit tests for Research Agent schemas, ranking, verification, and override."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.planning.schema import ExecutionPlan, PlanTask
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.research.ranking import rank_sources_data
from core.subgraphs.research.research_agent import (
    _evaluate_evidence,
    _execute_tool_call,
    _ResearchSession,
    configure_research_agent,
    run_research_agent,
)
from core.subgraphs.research.schema import ResearchFindings, SearchQueryBatch, TaskQueryPlan
from core.subgraphs.research.verification import verify_sources_data
from tests.helpers.research import default_research_agent_result, research_agent_override

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


@pytest.fixture(autouse=True)
def reset_research_agent() -> None:
    configure_research_agent(research_agent_override)
    yield
    configure_research_agent(None)


def _sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
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


def test_task_query_plan_requires_one_to_three_queries() -> None:
    with pytest.raises(ValidationError):
        TaskQueryPlan(task_order=1, task="Research fat loss training", queries=[])

    with pytest.raises(ValidationError, match="at most 3"):
        TaskQueryPlan(
            task_order=1,
            task="Research fat loss training",
            queries=[f"query {index}" for index in range(4)],
        )

    single = TaskQueryPlan(
        task_order=1,
        task="Research fat loss training",
        queries=["ACSM fat loss guideline"],
    )
    assert len(single.queries) == 1

    plan = TaskQueryPlan(
        task_order=1,
        task="Research fat loss training",
        queries=["ACSM fat loss guideline", "systematic review resistance training fat loss"],
    )
    assert len(plan.queries) == 2

    triple = TaskQueryPlan(
        task_order=1,
        task="Research fat loss training",
        queries=["query one", "query two", "query three"],
    )
    assert len(triple.queries) == 3


def test_search_query_batch_validation() -> None:
    batch = SearchQueryBatch(
        task_plans=[
            TaskQueryPlan(
                task_order=1,
                task="Research fat loss training volume",
                queries=["ACSM fat loss guideline", "hypertrophy fat loss review"],
            )
        ]
    )
    assert len(batch.task_plans) == 1


def test_search_query_batch_json_schema_omits_min_items() -> None:
    schema = SearchQueryBatch.model_json_schema()
    assert "minItems" not in str(schema)


def test_research_findings_coerces_numbered_string_lists() -> None:
    # key_findings arrives as a bare numbered string with no embedded URL on
    # either line. normalize_grounded_claim_items deliberately leaves such
    # items with source_url="" (see grounding/validate.py docstring) rather
    # than inventing one, and coerce_grounded_key_findings (schema.py) drops
    # any claim without its own valid source_url instead of borrowing one
    # from recommended_sources -- so both claims are dropped, not laundered
    # through a URL they were never actually checked against.
    findings = ResearchFindings(
        consensus="Resistance training supports fat loss with adequate protein intake.",
        key_findings="1. Higher protein preserves lean mass\n2. Strength training aids fat loss",
        conflicting_evidence="",
        limitations="Limited long-term RCTs in this population",
        recommended_sources=(
            "1. Comparison of concurrent training (https://example.com/study)\n"
            "2. Protein during caloric deficit (https://pmc.ncbi.nlm.nih.gov/articles/PMC9285060)"
        ),
    )
    assert findings.key_findings == []
    assert len(findings.recommended_sources) == 2
    assert "PMC9285060" in findings.recommended_sources[1]
    assert findings.conflicting_evidence == []
    assert len(findings.limitations) == 1


def test_research_findings_drops_claims_missing_their_own_source_url() -> None:
    """A claim dict with no source_url of its own must be dropped, not
    backfilled from recommended_sources -- the fallback was a citation-
    laundering hole (2026-07-30), the same pattern Phase 4 closed in
    grounding/validate.py's evidence-only allowlist."""
    findings = ResearchFindings(
        consensus="Resistance training supports fat loss with adequate protein intake.",
        key_findings=[
            {"claim": "Higher protein preserves lean mass", "source_url": ""},
            {"claim": "Strength training aids fat loss", "source_url": "https://example.com/real"},
        ],
        recommended_sources=["https://example.com/unrelated"],
    )
    assert len(findings.key_findings) == 1
    assert findings.key_findings[0].claim == "Strength training aids fat loss"
    assert findings.key_findings[0].source_url == "https://example.com/real"


def test_research_findings_allows_empty_key_findings() -> None:
    """A run with no fully evidence-supported claim is a legitimate, honest
    result -- not an error. See SYNTHESIS_SYSTEM_PROMPT's instruction to omit
    a claim entirely rather than fabricate one (2026-07-30)."""
    findings = ResearchFindings(
        consensus="No evidence document in this run supported a specific claim.",
        key_findings=[],
    )
    assert findings.key_findings == []


def test_hybrid_ranking_orders_by_composite_score() -> None:
    sources = [
        {
            "source_id": "a",
            "title": "General blog",
            "url": "https://example.com/blog",
            "snippet": "random content",
            "score": 0.95,
            "authority_score": 0.2,
        },
        {
            "source_id": "b",
            "title": "Systematic review of hypertrophy training",
            "url": "https://pubmed.ncbi.nlm.nih.gov/study",
            "snippet": "systematic review meta-analysis 2023",
            "score": 0.7,
            "authority_score": 1.0,
        },
    ]
    verified = verify_sources_data(sources)["sources"]
    ranked = rank_sources_data(verified)["sources"]
    assert ranked[0]["source_id"] == "b"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["composite_score"] >= ranked[1]["composite_score"]


def test_verify_sources_marks_whitelist_and_fitness_keyword() -> None:
    sources = [
        {
            "title": "NIH training study",
            "url": "https://www.nih.gov/fitness",
            "snippet": "training evidence",
        },
        {
            "title": "Other",
            "url": "https://example.com/other",
            "snippet": "finance",
        },
        {
            "title": "Training blog",
            "url": "https://example.com/training",
            "snippet": "hypertrophy workout",
        },
    ]
    result = verify_sources_data(sources)
    assert result["sources"][0]["verified"] is True
    assert result["sources"][0]["authority_tier"] == "whitelist"
    assert result["sources"][1]["verified"] is False
    assert result["sources"][2]["authority_tier"] == "fitness_keyword"


def test_run_research_agent_uses_override_without_llm() -> None:
    profile = {"goal": "fat_loss"}
    result = run_research_agent(
        query="lose weight",
        profile=profile,
        goal_spec=derive_goal_spec(profile),
        execution_plan=_sample_plan(),
    )
    assert result.agent_iterations == 1
    assert result.structured_findings.consensus
    assert len(result.sources) >= 1
    assert "Key findings" in result.evidence_summary


def test_configure_research_agent_override() -> None:
    custom = default_research_agent_result()
    configure_research_agent(lambda **kwargs: custom)
    profile: dict = {}
    result = run_research_agent(
        query="lose weight",
        profile=profile,
        goal_spec=derive_goal_spec(profile),
        execution_plan=_sample_plan(),
    )
    assert result == custom


def test_eval_skip_when_sufficient_verified_sources() -> None:
    sources = [
        {
            "title": "NIH training study",
            "url": "https://www.nih.gov/fitness",
            "snippet": "training evidence",
        },
        {
            "title": "PubMed review",
            "url": "https://pubmed.ncbi.nlm.nih.gov/study",
            "snippet": "systematic review",
        },
    ]
    evidence = [
        {"url": "https://www.nih.gov/fitness", "content": "Document one"},
        {"url": "https://pubmed.ncbi.nlm.nih.gov/study", "content": "Document two"},
    ]
    profile = {"goal": "fat_loss"}
    with patch(
        "core.subgraphs.research.research_agent.invoke_standard_structured_output"
    ) as mock_llm:
        result = _evaluate_evidence(
            query="lose weight",
            profile=profile,
            goal_spec=derive_goal_spec(profile),
            execution_plan=_sample_plan(),
            sources=sources,
            evidence=evidence,
        )
    assert result.sufficient is True
    assert result.gaps == []
    assert result.refined_queries == []
    mock_llm.assert_not_called()


def test_tavily_extract_respects_budget_and_failed_url_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _ResearchSession()
    session.max_total_extracts = 2
    calls: list[list[str]] = []

    def fake_extract(urls: list[str]) -> dict:
        calls.append(urls)
        return {"evidence": []}

    monkeypatch.setattr(
        "core.subgraphs.research.research_agent.extract_tavily_data",
        fake_extract,
    )

    first = _execute_tool_call(
        "tavily_extract",
        {"urls": ["https://pmc.ncbi.nlm.nih.gov/articles/PMC10620361"]},
        session,
    )
    second = _execute_tool_call(
        "tavily_extract",
        {"urls": ["https://pmc.ncbi.nlm.nih.gov/articles/PMC10620361"]},
        session,
    )
    third = _execute_tool_call(
        "tavily_extract",
        {"urls": ["https://pubmed.ncbi.nlm.nih.gov/123"]},
        session,
    )
    fourth = _execute_tool_call(
        "tavily_extract",
        {"urls": ["https://pubmed.ncbi.nlm.nih.gov/456"]},
        session,
    )

    assert len(calls) == 2
    assert "no_new_urls" in second
    assert "extract_budget_exhausted_or_duplicate" in fourth
    assert first
    assert third


def test_post_process_skips_tavily_when_local_evidence_is_sufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.subgraphs.research.utils import post_process_sources

    extract_called = False

    def fake_extract(urls: list[str]) -> dict:
        nonlocal extract_called
        extract_called = True
        return {"evidence": []}

    monkeypatch.setattr(
        "core.subgraphs.research.utils.extract_tavily_data",
        fake_extract,
    )
    sources = [
        {
            "title": "Lean bulk",
            "url": "local-kb://lean-bulk-surplus",
            "snippet": "lean bulk surplus",
            "provider": "local_kb",
            "verified": True,
        },
        {
            "title": "Hypertrophy volume",
            "url": "local-kb://hypertrophy-volume-guideline",
            "snippet": "hypertrophy volume",
            "provider": "local_kb",
            "verified": True,
        },
    ]
    evidence = [
        {"url": "local-kb://lean-bulk-surplus", "content": "doc one", "provider": "local_kb"},
    ]
    ranked, merged = post_process_sources(sources, evidence)
    assert extract_called is False
    assert len(ranked) == 2
    assert len(merged) == 1
