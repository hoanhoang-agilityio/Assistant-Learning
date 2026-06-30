import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.mcp.tavily_client import (
    TAVILY_EXTRACT_TOOL,
    TAVILY_SEARCH_TOOL,
    get_tavily_client,
)
from core.observability.tracing import tavily_mcp_span_context
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.planning.utils import (
    execution_plan_to_todo_strings,
    has_execution_plan,
    load_execution_plan,
)
from core.vfs import VFS

TRUSTED_DOMAIN_SUFFIXES = (".edu", ".gov", ".org")
FITNESS_KEYWORDS = (
    "fitness",
    "training",
    "exercise",
    "hypertrophy",
    "strength",
    "macro",
    "nutrition",
    "workout",
)


class ResearchTodosGateError(ValueError):
    """Raised when research is invoked before a planning execution plan exists."""


def build_research_questions(query: str, plan: ExecutionPlan) -> list[str]:
    ordered = sorted(plan.tasks, key=lambda task: task.order)
    return [f"{task.task} (rationale: {task.rationale}; user query: {query})" for task in ordered]


def assert_todos_gate(todos: list[str]) -> None:
    if not todos:
        raise ResearchTodosGateError(
            "Research blocked: plan/execution_plan.json is required before retrieval"
        )


def normalize_search_results(raw_result: dict[str, Any], question: str) -> list[dict[str, Any]]:
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
                "source_id": f"{question}:{index}",
                "title": str(item.get("title", "Untitled source")),
                "url": url,
                "snippet": str(item.get("content", item.get("snippet", ""))),
                "score": float(item.get("score", 0.0) or 0.0),
                "provider": "tavily",
                "research_question": question,
            }
        )
    return normalized


def search_evidence_data(research_questions: list[str], todos: list[str]) -> dict[str, Any]:
    assert_todos_gate(todos)
    client = get_tavily_client()
    sources: list[dict[str, Any]] = []
    for question in research_questions:
        with tavily_mcp_span_context(TAVILY_SEARCH_TOOL, input_data={"query": question}):
            search_result = client.search(question)
        sources.extend(normalize_search_results(search_result, question))
    return {"sources": sources}


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


def retrieve_documents_data(source_ids: list[str], sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not source_ids:
        return {"evidence": []}

    selected_urls = [
        source["url"]
        for source in sources
        if source.get("source_id") in source_ids and source.get("url")
    ]
    if not selected_urls:
        return {"evidence": []}

    client = get_tavily_client()
    with tavily_mcp_span_context(TAVILY_EXTRACT_TOOL, input_data={"urls": selected_urls}):
        extract_result = client.extract(selected_urls)
    return {"evidence": normalize_extract_results(extract_result)}


def rank_sources_data(sources: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_sources = sorted(sources, key=lambda source: source.get("score", 0.0), reverse=True)
    for index, source in enumerate(ranked_sources, start=1):
        source["rank"] = index
    return {"sources": ranked_sources}


def _is_trusted_domain(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(hostname.endswith(suffix) for suffix in TRUSTED_DOMAIN_SUFFIXES)


def _is_fitness_relevant(source: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(source.get("title", "")),
            str(source.get("snippet", "")),
            str(source.get("url", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in FITNESS_KEYWORDS)


def verify_sources_data(sources: list[dict[str, Any]]) -> dict[str, Any]:
    verified_sources: list[dict[str, Any]] = []
    for source in sources:
        verified_source = dict(source)
        is_trusted = _is_trusted_domain(source.get("url", ""))
        verified_source["verified"] = is_trusted or _is_fitness_relevant(source)
        verified_sources.append(verified_source)
    return {"sources": verified_sources}


def build_evidence_summary(sources: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    verified_count = sum(1 for source in sources if source.get("verified"))
    return (
        f"Collected {len(sources)} sources and {len(evidence)} documents "
        f"({verified_count} verified for fitness relevance)."
    )


def write_research_artifacts(
    workspace_path: str,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    evidence_summary: str,
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("research/sources.json", json.dumps(sources, indent=2))
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "evidence": evidence,
                "evidence_summary": evidence_summary,
                "source_count": len(sources),
            },
            indent=2,
        ),
    )


def load_execution_plan_for_research(workspace_path: str) -> ExecutionPlan | None:
    if not has_execution_plan(workspace_path):
        return None
    return load_execution_plan(workspace_path)


def load_todos_for_research(workspace_path: str) -> list[str]:
    """Derive ordered task strings from the execution plan for legacy tool signatures."""
    plan = load_execution_plan_for_research(workspace_path)
    if plan is None:
        return []
    return execution_plan_to_todo_strings(plan)
