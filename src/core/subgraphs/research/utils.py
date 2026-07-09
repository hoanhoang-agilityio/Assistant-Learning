"""Research subgraph utilities: MCP adapters, VFS I/O, and post-processing."""

import json
import logging
from pathlib import Path
from typing import Any

from core.config.settings import get_settings
from core.llm.contracts import validate_research_context_payload
from core.llm.serializers import compact_execution_plan_for_llm, compact_profile_for_llm
from core.mcp.tavily_client import (
    TAVILY_EXTRACT_TOOL,
    TAVILY_SEARCH_TOOL,
    get_tavily_client,
)
from core.observability.tracing import traced_tavily_call
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.planning.utils import (
    execution_plan_to_todo_strings,
    has_execution_plan,
    load_execution_plan,
)
from core.subgraphs.research.query_cache import get_cached_search_result, store_search_result
from core.subgraphs.research.ranking import rank_sources_data
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.research.verification import verify_sources_data
from core.vfs import VFS

logger = logging.getLogger(__name__)


class ResearchTodosGateError(ValueError):
    """Raised when research is invoked before a planning execution plan exists."""


def assert_execution_plan_gate(workspace_path: str) -> None:
    if not has_execution_plan(workspace_path):
        raise ResearchTodosGateError(
            "Research blocked: plan/execution_plan.json is required before retrieval"
        )


def assert_todos_gate(todos: list[str]) -> None:
    """Deprecated: prefer assert_execution_plan_gate."""
    if not todos:
        raise ResearchTodosGateError(
            "Research blocked: plan/execution_plan.json is required before retrieval"
        )


def load_profile_for_research(workspace_path: str) -> dict[str, Any]:
    """Load validated profile from planning VFS artifacts."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("plan/profile.json"):
        return {}
    return json.loads(vfs.read("plan/profile.json"))


def load_execution_plan_for_research(workspace_path: str) -> ExecutionPlan | None:
    if not has_execution_plan(workspace_path):
        return None
    return load_execution_plan(workspace_path)


def load_existing_research(workspace_path: str) -> dict[str, Any] | None:
    """Load prior research artifacts when a partial rerun re-enters Research."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("research/sources.json"):
        return None
    sources = json.loads(vfs.read("research/sources.json"))
    evidence: list[dict[str, Any]] = []
    if vfs.exists("research/findings.json"):
        findings_payload = json.loads(vfs.read("research/findings.json"))
        evidence = findings_payload.get("evidence") or []
    return {"sources": sources, "evidence": evidence}


def is_local_kb_url(url: str) -> bool:
    """Return True when a URL points at the local knowledge base."""
    normalized = url.strip().lower()
    return normalized.startswith("local-kb://")


def has_sufficient_research_coverage(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> bool:
    """Return True when gathered sources and evidence meet skip-eval thresholds."""
    settings = get_settings()
    verified_sources = verify_sources_data(sources)["sources"]
    verified_count = sum(1 for source in verified_sources if source.get("verified"))
    return (
        len(sources) >= settings.research_min_verified_sources_for_skip_eval
        and verified_count >= settings.research_min_verified_sources_for_skip_eval
        and len(evidence) >= settings.research_min_evidence_docs_for_skip_eval
    )


def load_todos_for_research(workspace_path: str) -> list[str]:
    """Derive ordered task strings from the execution plan for legacy tool signatures."""
    plan = load_execution_plan_for_research(workspace_path)
    if plan is None:
        return []
    return execution_plan_to_todo_strings(plan)


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


def build_eval_llm_extra(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    sources_limit: int = 10,
    evidence_limit: int = 5,
    snippet_chars: int = 200,
    content_chars: int = 300,
) -> dict[str, Any]:
    """Build compact eval-phase extra fields without redundant metadata."""
    return {
        "sources_preview": compact_sources_for_llm(
            sources,
            limit=sources_limit,
            snippet_chars=snippet_chars,
        ),
        "evidence_preview": [
            {
                "url": item.get("url"),
                "content_preview": str(item.get("content", ""))[:content_chars],
            }
            for item in evidence[:evidence_limit]
        ],
    }


def build_synthesis_llm_extra(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build synthesis extra fields with URL deduplication between sources and evidence."""
    settings = get_settings()
    evidence_limit = settings.research_synthesis_evidence_limit
    content_chars = settings.research_synthesis_content_chars
    evidence_docs = [
        {
            "url": item.get("url"),
            "content": str(item.get("content", ""))[:content_chars],
        }
        for item in evidence[:evidence_limit]
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
    return {
        "evidence": evidence_docs,
        "source_catalog": source_catalog,
    }


def build_goal_context(profile: dict[str, Any]) -> dict[str, Any]:
    """Return compact goal/timeline context for research payloads."""
    return {
        key: profile[key]
        for key in (
            "goal",
            "goal_archetype",
            "horizon_weeks",
            "weekly_rate_kg",
            "weight_delta_kg",
            "feasibility_level",
        )
        if profile.get(key) not in (None, "")
    }


def build_research_context_payload(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    execution_plan: ExecutionPlan | None = None,
    include_task_rationale: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deduplicated payload for Research Agent LLM calls."""
    payload: dict[str, Any] = {"profile": compact_profile_for_llm(profile)}
    goal_context = build_goal_context(profile)
    if goal_context:
        payload["goal_context"] = goal_context
    stripped_query = query.strip()
    if stripped_query:
        payload["query"] = stripped_query
    if request_type and request_type != profile.get("goal"):
        payload["request_type"] = request_type
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


def normalize_search_results(raw_result: dict[str, Any], query: str) -> list[dict[str, Any]]:
    results = raw_result.get("results", raw_result.get("search_results", []))
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", ""))
        normalized.append(
            {
                "source_id": f"{query}:{index}",
                "title": str(item.get("title", "Untitled source")),
                "url": url,
                "snippet": str(item.get("content", item.get("snippet", ""))),
                "score": float(item.get("score", 0.0) or 0.0),
                "provider": "tavily",
                "research_query": query,
            }
        )
    return normalized


def search_tavily_data(query: str) -> dict[str, Any]:
    """Run a single Tavily search query and return normalized sources.

    Cached by normalized query text for a short TTL — catches identical
    queries issued from different execution-plan tasks or different runs.
    """
    cached = get_cached_search_result(query)
    if cached is not None:
        return cached

    client = get_tavily_client()
    with traced_tavily_call(TAVILY_SEARCH_TOOL, input_data={"query": query}) as span:
        search_result = client.search(query)
        sources = normalize_search_results(search_result, query)
        if span is not None:
            raw_keys = sorted(search_result.keys()) if isinstance(search_result, dict) else []
            span.update(
                output={
                    "source_count": len(sources),
                    "sources": sources[:5],
                    "raw_keys": raw_keys,
                }
            )
        if not sources:
            logger.warning("Tavily search returned no sources for query: %s", query[:120])
    result = {"sources": sources, "query": query}
    store_search_result(query, result)
    return result


def normalize_extract_results(raw_result: dict[str, Any]) -> list[dict[str, Any]]:
    results = raw_result.get("results", [])
    if not isinstance(results, list):
        return []

    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "document_id": f"doc_{index}",
                "url": str(item.get("url", "")),
                "content": str(item.get("raw_content", item.get("content", ""))),
                "provider": "tavily",
            }
        )
    return evidence


def extract_tavily_data(urls: list[str]) -> dict[str, Any]:
    """Extract document content for the given URLs via Tavily MCP."""
    cleaned_urls = [url for url in urls if url]
    if not cleaned_urls:
        return {"evidence": []}

    client = get_tavily_client()
    with traced_tavily_call(TAVILY_EXTRACT_TOOL, input_data={"urls": cleaned_urls}) as span:
        extract_result = client.extract(cleaned_urls)
        evidence = normalize_extract_results(extract_result)
        if span is not None:
            span.update(
                output={
                    "document_count": len(evidence),
                    "urls": cleaned_urls,
                    "raw_keys": sorted(extract_result.keys())
                    if isinstance(extract_result, dict)
                    else [],
                }
            )
        if not evidence:
            logger.warning("Tavily extract returned no documents for urls: %s", cleaned_urls)
    return {"evidence": evidence}


def dedupe_sources_by_url(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-scoring source per URL."""
    by_url: dict[str, dict[str, Any]] = {}
    for source in sources:
        url = str(source.get("url", ""))
        if not url:
            continue
        existing = by_url.get(url)
        if existing is None or float(source.get("score", 0.0)) > float(existing.get("score", 0.0)):
            by_url[url] = source
    return list(by_url.values())


def post_process_sources(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    extract_top_k: int | None = None,
    max_extracts_remaining: int | None = None,
    failed_extract_urls: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Dedupe, verify, rank, and extract top-K ranked URLs not yet in evidence."""
    settings = get_settings()
    top_k = extract_top_k if extract_top_k is not None else settings.research_extract_top_k

    deduped = dedupe_sources_by_url(sources)
    verified = verify_sources_data(deduped)["sources"]
    ranked = rank_sources_data(verified)["sources"]

    if has_sufficient_research_coverage(ranked, evidence):
        return ranked, _merge_evidence_by_url(evidence)

    extracted_urls = {str(item.get("url", "")) for item in evidence if item.get("url")}
    blocked_urls = failed_extract_urls or set()
    remaining_extracts = (
        max_extracts_remaining
        if max_extracts_remaining is not None
        else settings.research_max_total_extracts
    )
    urls_to_extract: list[str] = []
    for source in ranked[:top_k]:
        url = str(source.get("url", ""))
        if not url or is_local_kb_url(url):
            continue
        if url in extracted_urls or url in blocked_urls:
            continue
        if remaining_extracts <= 0:
            break
        urls_to_extract.append(url)
        remaining_extracts -= 1

    additional_evidence: list[dict[str, Any]] = []
    if urls_to_extract:
        additional_evidence = extract_tavily_data(urls_to_extract)["evidence"]

    merged_evidence = _merge_evidence_by_url(evidence + additional_evidence)
    return ranked, merged_evidence


def _merge_evidence_by_url(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(evidence):
        url = str(item.get("url", ""))
        key = url or f"doc_{index}"
        if key not in by_url:
            by_url[key] = item
    return list(by_url.values())


def derive_evidence_summary(findings: ResearchFindings) -> str:
    """Build backward-compatible evidence_summary from structured findings."""
    lines = [findings.consensus]
    if findings.key_findings:
        lines.append("")
        lines.append("Key findings:")
        for finding in findings.key_findings[:3]:
            lines.append(f"- {finding}")
    return "\n".join(lines)


def write_research_artifacts(
    workspace_path: str,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    structured_findings: ResearchFindings,
    evidence_summary: str,
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("research/sources.json", json.dumps(sources, indent=2))
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "structured_findings": structured_findings.model_dump(),
                "evidence": evidence,
                "evidence_summary": evidence_summary,
                "source_count": len(sources),
                "local_source_count": sum(
                    1 for source in sources if source.get("provider") == "local_kb"
                ),
            },
            indent=2,
        ),
    )
