"""Building the compacted LLM payloads research sends to the evaluation and
synthesis calls."""

import logging
from typing import Any

from core.config.settings import get_settings
from core.llm.contracts import validate_research_context_payload
from core.llm.serializers import (
    compact_execution_plan_for_llm,
    compact_goal_spec_for_llm,
    compact_profile_for_llm,
)
from core.planning.schema import ExecutionPlan
from core.profile.goal_spec import GoalSpec
from core.subgraphs.research.compression import compress_content, query_terms, score_content

logger = logging.getLogger(__name__)


def compact_source_for_llm(
    source: dict[str, Any],
    *,
    snippet_chars: int = 200,
) -> dict[str, str]:
    """Return minimal source fields for LLM payloads."""
    snippet = str(source.get("snippet", ""))
    return {
        "title": str(source.get("title", "Untitled source")),
        "url": str(source.get("url", "")),
        "snippet": snippet[:snippet_chars],
    }


def compact_sources_for_llm(
    sources: list[dict[str, Any]],
    *,
    limit: int | None = None,
    snippet_chars: int = 200,
) -> list[dict[str, str]]:
    """Return compact source previews for LLM payloads."""
    selected = sources if limit is None else sources[:limit]
    return [compact_source_for_llm(source, snippet_chars=snippet_chars) for source in selected]


def _rank_evidence_by_relevance(
    evidence: list[dict[str, Any]], terms: frozenset[str]
) -> list[dict[str, Any]]:
    """Order evidence docs by relevance to the query before truncating to a
    limit, instead of keeping whichever docs happened to be extracted/merged
    first -- a document's position here has never meant "most relevant"."""
    return sorted(
        evidence,
        key=lambda item: score_content(str(item.get("content", "")), terms),
        reverse=True,
    )


def build_eval_llm_extra(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    query: str = "",
    sources_limit: int = 10,
    evidence_limit: int = 5,
    snippet_chars: int = 200,
    content_chars: int = 300,
) -> dict[str, Any]:
    """Build compact eval-phase extra fields without redundant metadata."""
    terms = query_terms(query)
    ranked_evidence = _rank_evidence_by_relevance(evidence, terms)
    return {
        "sources_preview": compact_sources_for_llm(
            sources,
            limit=sources_limit,
            snippet_chars=snippet_chars,
        ),
        "evidence_preview": [
            {
                "url": item.get("url"),
                "content_preview": compress_content(
                    str(item.get("content", "")), max_chars=content_chars, terms=terms
                ),
            }
            for item in ranked_evidence[:evidence_limit]
        ],
    }


def build_synthesis_llm_extra(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    query: str = "",
    verification_feedback: str | None = None,
) -> dict[str, Any]:
    """Build synthesis extra fields with URL deduplication between sources and evidence.

    `verification_feedback` (L1 Phase 4) is only ever set by the Policy Engine's
    automatic retry (`verification_failed_auto_retry`, see policy_engine.py) --
    a previous synthesis in this same run produced a citation/faithfulness
    problem, and this is that failure's feedback text so the LLM can actually
    address the specific issue instead of blindly retrying the same mistake.

    `query` (L1 Phase 4, evidence compression) scores relevance for both which
    evidence docs make the cut and which sentences within each survive
    truncation -- see core.subgraphs.research.compression for why blind
    first-N-docs/first-N-chars truncation was a real faithfulness risk, not
    just a cost-control detail.
    """
    settings = get_settings()
    evidence_limit = settings.research_synthesis_evidence_limit
    content_chars = settings.research_synthesis_content_chars
    terms = query_terms(query)
    ranked_evidence = _rank_evidence_by_relevance(evidence, terms)
    evidence_docs = [
        {
            "url": item.get("url"),
            "content": compress_content(
                str(item.get("content", "")), max_chars=content_chars, terms=terms
            ),
        }
        for item in ranked_evidence[:evidence_limit]
    ]
    evidence_urls = {str(item.get("url", "")) for item in evidence_docs if item.get("url")}
    source_catalog = compact_sources_for_llm(
        [
            source
            for source in sources
            if str(source.get("url", "")) and str(source.get("url", "")) not in evidence_urls
        ],
        limit=5,
    )
    extra: dict[str, Any] = {
        "evidence": evidence_docs,
        "source_catalog": source_catalog,
    }
    if verification_feedback:
        extra["verification_feedback"] = verification_feedback
    return extra


def build_goal_context(profile: dict[str, Any], goal_spec: GoalSpec) -> dict[str, Any]:
    """Return compact goal/timeline context for research payloads.

    `goal_spec` must be derived by the caller from this same `profile` -- see the
    single-derivation threading rule in core/profile/goal_spec.py.
    """
    goal_context = {
        "goal": profile.get("goal"),
        "horizon_weeks": profile.get("horizon_weeks"),
        **compact_goal_spec_for_llm(goal_spec),
    }
    return {key: value for key, value in goal_context.items() if value not in (None, "")}


def build_research_context_payload(
    *,
    query: str,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    execution_plan: ExecutionPlan | None = None,
    include_task_rationale: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deduplicated payload for Research Agent LLM calls."""
    payload: dict[str, Any] = {"profile": compact_profile_for_llm(profile)}
    goal_context = build_goal_context(profile, goal_spec)
    if goal_context:
        payload["goal_context"] = goal_context
    stripped_query = query.strip()
    if stripped_query:
        payload["query"] = stripped_query
    if execution_plan is not None:
        payload.update(
            compact_execution_plan_for_llm(
                execution_plan,
                include_task_rationale=include_task_rationale,
            )
        )
    if extra:
        payload.update(extra)
    validate_research_context_payload(payload)
    return payload
