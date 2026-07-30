"""Post-processing gathered sources: dedupe, verify, rank, compress, summarise."""

import logging
from typing import Any

from core.config.settings import get_settings
from core.subgraphs.research.guidelines import (
    has_sufficient_research_coverage,
    is_local_kb_url,
)
from core.subgraphs.research.ranking import rank_sources_data
from core.subgraphs.research.schema import ResearchFindings
from core.subgraphs.research.tavily import extract_tavily_data
from core.subgraphs.research.verification import (
    verify_sources_data,
)

logger = logging.getLogger(__name__)


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
        for finding in findings.key_findings[:5]:
            lines.append(f"- {finding.claim} ({finding.source_url})")
    return "\n".join(lines)
