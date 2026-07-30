"""Deterministic grounding validation — drop claims with missing/unknown sources."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from core.grounding.schema import GroundedClaim


def allowed_source_urls(*, evidence: list[dict[str, Any]] | None = None) -> set[str]:
    """Build the allowlist of source URLs a grounded claim may cite.

    Deliberately `evidence` only -- `evidence` is the sole guarantee that a
    URL's content was actually retrieved and is available to ground a claim
    against. This used to also merge in `sources` (every raw search-engine
    hit, most never fetched/read in full) and `recommended_sources` (the same
    synthesis LLM call's own output). Both let a claim "launder" an
    unsupported citation through the allowlist check: a URL that merely
    showed up in search results, or that the same hallucinating call also
    happened to list as "recommended", is not evidence the claim is grounded.
    Found 2026-07-30 via a real production run whose key_findings cited 4
    URLs with zero overlap with its own evidence array -- all 4 passed the
    old allowlist purely because they also appeared in `sources`/
    `recommended_sources`. See docs/reports/known_limitations_remediation_plan.md, L1 (Phase 4).
    """
    urls: set[str] = set()
    for item in evidence or []:
        url = _normalize_url(item.get("url"))
        if url:
            urls.add(url)
    return urls


def _coerce_string_list(value: Any) -> list[str]:
    """Normalize prose/numbered strings into a list of claim texts."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    lines = re.split(r"\n+", text)
    items: list[str] = []
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned).strip()
        if cleaned:
            items.append(cleaned)
    if items:
        return items
    cleaned = re.sub(r"^\d+[\.\)]\s*", "", text).strip()
    return [cleaned] if cleaned else []


def normalize_grounded_claim_items(raw_items: Any) -> list[dict[str, Any]]:
    """Coerce LLM/legacy payloads into dicts shaped like GroundedClaim.

    Accepts list[GroundedClaim], list[dict], list[str], or a single prose string
    (numbered / bulleted lines). String-only items keep an empty source_url so
    callers can attach URLs or filter them out.
    """
    if raw_items is None:
        return []
    if isinstance(raw_items, str):
        return [{"claim": text, "source_url": ""} for text in _coerce_string_list(raw_items)]
    if not isinstance(raw_items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, GroundedClaim):
            normalized.append(item.model_dump())
            continue
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"claim": text, "source_url": ""})
            continue
        if isinstance(item, dict):
            claim = str(item.get("claim") or item.get("text") or "").strip()
            source_url = str(item.get("source_url") or item.get("url") or "").strip()
            finding_id = item.get("finding_id")
            if not claim:
                continue
            payload: dict[str, Any] = {"claim": claim, "source_url": source_url}
            if finding_id is not None and str(finding_id).strip():
                payload["finding_id"] = str(finding_id).strip()
            normalized.append(payload)
    return normalized


def filter_grounded_claims(
    claims: list[GroundedClaim] | list[dict[str, Any]] | Any,
    allowed_urls: set[str],
) -> list[GroundedClaim]:
    """Keep only claims whose source_url is in the allowlist."""
    if not allowed_urls:
        return []
    normalized = normalize_grounded_claim_items(claims)
    kept: list[GroundedClaim] = []
    seen: set[tuple[str, str]] = set()
    for item in normalized:
        url = _normalize_url(item.get("source_url"))
        claim = str(item.get("claim", "")).strip()
        if not claim or not url or url not in allowed_urls:
            continue
        key = (claim.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        finding_id = item.get("finding_id")
        kept.append(
            GroundedClaim(
                claim=claim,
                source_url=url,
                finding_id=str(finding_id).strip() if finding_id else None,
            )
        )
    return kept


def assign_finding_ids(claims: list[GroundedClaim], *, prefix: str = "kf") -> list[GroundedClaim]:
    """Stamp stable finding_id values when missing (research → planner traceability)."""
    assigned: list[GroundedClaim] = []
    for index, claim in enumerate(claims):
        finding_id = claim.finding_id or f"{prefix}_{index}"
        assigned.append(claim.model_copy(update={"finding_id": finding_id}))
    return assigned


def _normalize_url(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return text
    # local-kb:// and similar non-http schemes used by citation checks
    if "://" in text:
        return text
    return text
