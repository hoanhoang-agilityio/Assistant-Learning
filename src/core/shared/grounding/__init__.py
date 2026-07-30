"""Shared evidence-grounding contract used by research, fitness, and verification."""

from core.shared.grounding.finalize import extract_source_url, finalize_structured_findings
from core.shared.grounding.render import (
    render_grounded_claims_json,
    render_grounded_claims_json_text,
    render_grounded_claims_markdown,
)
from core.shared.grounding.schema import GroundedClaim
from core.shared.grounding.validate import (
    allowed_source_urls,
    assign_finding_ids,
    filter_grounded_claims,
    normalize_grounded_claim_items,
)

__all__ = [
    "GroundedClaim",
    "allowed_source_urls",
    "assign_finding_ids",
    "extract_source_url",
    "filter_grounded_claims",
    "finalize_structured_findings",
    "normalize_grounded_claim_items",
    "render_grounded_claims_json",
    "render_grounded_claims_json_text",
    "render_grounded_claims_markdown",
]
