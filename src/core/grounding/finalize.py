"""Helpers that attach and filter grounded findings after research synthesis."""

from __future__ import annotations

import re
from typing import Any

from core.grounding.validate import (
    allowed_source_urls,
    assign_finding_ids,
    filter_grounded_claims,
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
) -> Any:
    """Filter key_findings to allowlisted URLs and stamp finding_id values.

    Orphan claims (a source_url not in the allowlist) are dropped, not rebound
    to a fallback URL (2026-07-30 L1 Phase 4: rebinding was found to silently
    misattribute a claim to a URL its own text was never actually about --
    the fix that closed the "recommended_sources" laundering loophole
    (see allowed_source_urls) would otherwise have just re-introduced the same
    kind of misattribution one step later, via this fallback). Planner-side
    validation is the same strict drop-only filter_grounded_claims call.

    The allowlist is `evidence`-only (see allowed_source_urls) -- no longer
    also built from `sources`/`recommended_sources`, which let a claim cite a
    URL that was merely found by search (or self-declared "recommended" by
    this same synthesis call) without its content ever having been retrieved.
    """
    from core.subgraphs.research.schema import ResearchFindings

    if not isinstance(findings, ResearchFindings):
        findings = ResearchFindings.model_validate(findings)
    allow = allowed_source_urls(evidence=evidence)
    if not allow:
        return findings.model_copy(
            update={"key_findings": assign_finding_ids(list(findings.key_findings))}
        )
    filtered = assign_finding_ids(filter_grounded_claims(findings.key_findings, allow), prefix="kf")
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
