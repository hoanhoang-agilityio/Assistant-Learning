"""Deterministic renderers for grounded claims (no LLM markdown)."""

from __future__ import annotations

import json
from typing import Any

from core.grounding.schema import GroundedClaim


def render_grounded_claims_markdown(claims: list[GroundedClaim]) -> str:
    """Render grounded claims as markdown for faithfulness scoring and plan embeds."""
    if not claims:
        return "# Grounded Claims\n\nNo grounded research claims available.\n"
    lines = ["# Grounded Claims", ""]
    lines.append("## Evidence Applied")
    lines.append("")
    for claim in claims:
        finding = f" ({claim.finding_id})" if claim.finding_id else ""
        lines.append(f"- {claim.claim}{finding}")
        lines.append(f"  - Source: {claim.source_url}")
    lines.append("")
    lines.append("## Evidence Summary")
    lines.append("")
    for claim in claims:
        lines.append(f"- {claim.claim} ({claim.source_url})")
    lines.append("")
    return "\n".join(lines)


def render_grounded_claims_json(claims: list[GroundedClaim]) -> dict[str, Any]:
    """JSON artifact payload for fitness/grounded_claims.json."""
    return {
        "claims": [claim.model_dump() for claim in claims],
        "claim_count": len(claims),
    }


def render_grounded_claims_json_text(claims: list[GroundedClaim]) -> str:
    """Serialize grounded claims JSON for VFS writes."""
    return json.dumps(render_grounded_claims_json(claims), indent=2)
