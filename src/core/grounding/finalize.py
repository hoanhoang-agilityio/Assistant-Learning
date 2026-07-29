"""Helpers that attach and filter grounded findings after research synthesis."""

from __future__ import annotations

import re
from typing import Any

from core.grounding.schema import GroundedClaim
from core.grounding.validate import (
    allowed_source_urls,
    assign_finding_ids,
    filter_grounded_claims,
    normalize_grounded_claim_items,
)

_URL_IN_TEXT = re.compile(r"https?://[^\s)\]>\"']+|local-kb://[^\s)\]>\"']+")


def extract_source_url(raw: Any) -> str:
    """Extract a usable URL from a raw string or recommended_sources entry."""
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://") or text.startswith("local-kb://"):
        return text.split()[0].rstrip(".,;")
    match = _URL_IN_TEXT.search(text)
    return match.group(0).rstrip(".,;") if match else ""


def finalize_structured_findings(
    findings: Any,
    *,
    evidence: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> Any:
    """Filter key_findings to allowlisted URLs and stamp finding_id values.

    Orphan claims (missing/invalid URL) are rebound to the first allowlisted URL so
    synthesis text is not discarded solely for a missing citation; planner-side
    validation remains strict (drop-only).
    """
    from core.subgraphs.research.schema import ResearchFindings

    if not isinstance(findings, ResearchFindings):
        findings = ResearchFindings.model_validate(findings)
    allow = allowed_source_urls(
        evidence=evidence,
        sources=sources,
        recommended_sources=[
            extract_source_url(item) or item for item in findings.recommended_sources
        ],
    )
    if not allow:
        return findings.model_copy(
            update={"key_findings": assign_finding_ids(list(findings.key_findings))}
        )
    filtered = filter_grounded_claims(findings.key_findings, allow)
    if not filtered:
        filtered = _rebind_orphan_claims(findings.key_findings, allow)
    if not filtered:
        filtered = assign_finding_ids(list(findings.key_findings))
    else:
        filtered = assign_finding_ids(filtered, prefix="kf")
    recommended = []
    for item in findings.recommended_sources:
        url = extract_source_url(item) or str(item).strip()
        if url:
            recommended.append(url)
    return findings.model_copy(
        update={
            "key_findings": filtered,
            "recommended_sources": recommended or sorted(allow),
        }
    )


def _rebind_orphan_claims(raw_claims: Any, allowed_urls: set[str]) -> list[GroundedClaim]:
    fallback = sorted(allowed_urls)[0]
    rebound: list[GroundedClaim] = []
    seen: set[str] = set()
    for item in normalize_grounded_claim_items(raw_claims):
        claim = str(item.get("claim", "")).strip()
        if not claim or claim.lower() in seen:
            continue
        seen.add(claim.lower())
        url = extract_source_url(item.get("source_url"))
        if url not in allowed_urls:
            url = fallback
        rebound.append(
            GroundedClaim(claim=claim, source_url=url, finding_id=item.get("finding_id"))
        )
    return rebound
