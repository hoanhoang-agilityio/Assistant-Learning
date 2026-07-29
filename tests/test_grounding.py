"""Unit tests for shared grounding contract and deterministic validation/render."""

from core.grounding import (
    GroundedClaim,
    allowed_source_urls,
    filter_grounded_claims,
    finalize_structured_findings,
    render_grounded_claims_markdown,
)
from core.subgraphs.research.schema import ResearchFindings


def test_filter_grounded_claims_drops_unknown_urls() -> None:
    allow = {"https://example.edu/a"}
    claims = [
        GroundedClaim(claim="Supported claim.", source_url="https://example.edu/a"),
        GroundedClaim(claim="Invented claim.", source_url="https://evil.example/x"),
    ]
    kept = filter_grounded_claims(claims, allow)
    assert len(kept) == 1
    assert kept[0].claim == "Supported claim."


def test_allowed_source_urls_merges_evidence_and_recommended() -> None:
    allow = allowed_source_urls(
        evidence=[{"url": "https://example.edu/e"}],
        sources=[{"url": "https://example.edu/s"}],
        recommended_sources=["https://example.edu/r"],
    )
    assert allow == {
        "https://example.edu/e",
        "https://example.edu/s",
        "https://example.edu/r",
    }


def test_render_grounded_claims_markdown_is_deterministic() -> None:
    markdown = render_grounded_claims_markdown(
        [
            GroundedClaim(
                claim="Train 3 days per week.",
                source_url="https://example.edu/a",
                finding_id="kf_0",
            )
        ]
    )
    assert markdown.startswith("# Grounded Claims")
    assert "## Evidence Applied" in markdown
    assert "## Evidence Summary" in markdown
    assert "https://example.edu/a" in markdown
    assert "kf_0" in markdown


def test_finalize_structured_findings_assigns_finding_ids() -> None:
    findings = ResearchFindings(
        consensus="Resistance training supports fat loss with adequate protein intake.",
        key_findings=[
            {
                "claim": "Higher protein preserves lean mass",
                "source_url": "https://example.edu/a",
            }
        ],
        recommended_sources=["https://example.edu/a"],
    )
    finalized = finalize_structured_findings(
        findings,
        evidence=[{"url": "https://example.edu/a", "content": "protein preserves lean mass"}],
        sources=[{"url": "https://example.edu/a"}],
    )
    assert finalized.key_findings[0].finding_id == "kf_0"
