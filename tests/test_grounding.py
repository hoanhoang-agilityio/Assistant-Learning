"""Unit tests for shared grounding contract and deterministic validation/render."""

import pytest

from core.capabilities.research.schema import ResearchFindings
from core.shared.grounding import (
    GroundedClaim,
    allowed_source_urls,
    filter_grounded_claims,
    finalize_structured_findings,
    render_grounded_claims_markdown,
)


def test_filter_grounded_claims_drops_unknown_urls() -> None:
    allow = {"https://example.edu/a"}
    claims = [
        GroundedClaim(claim="Supported claim.", source_url="https://example.edu/a"),
        GroundedClaim(claim="Invented claim.", source_url="https://evil.example/x"),
    ]
    kept = filter_grounded_claims(claims, allow)
    assert len(kept) == 1
    assert kept[0].claim == "Supported claim."


def test_allowed_source_urls_is_evidence_only() -> None:
    """evidence-only, deliberately: a URL merely found by search (`sources`) or
    self-declared "recommended" by the same synthesis call must not count as
    grounding -- only a URL whose content was actually retrieved (evidence)
    does. See allowed_source_urls's docstring for the real-run bug this fixes."""
    allow = allowed_source_urls(evidence=[{"url": "https://example.edu/e"}])
    assert allow == {"https://example.edu/e"}


def test_allowed_source_urls_does_not_accept_sources_or_recommended_kwargs() -> None:
    with pytest.raises(TypeError):
        allowed_source_urls(  # type: ignore[call-arg]
            evidence=[{"url": "https://example.edu/e"}],
            sources=[{"url": "https://example.edu/s"}],
        )


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
    )
    assert finalized.key_findings[0].finding_id == "kf_0"


def test_finalize_structured_findings_drops_a_claim_only_recommended_not_evidenced() -> None:
    """Regression test for the real bug found 2026-07-30 (run_c3b8e3e9cb): a
    claim citing a URL that was merely searched (or self-"recommended") but
    never actually retrieved as evidence must not pass the allowlist purely
    because it was also self-declared "recommended" by the same synthesis
    call. It is now a true orphan claim and is dropped, not rebound to a
    fallback evidence URL (L1 Phase 4 priority #1: drop, not rebind --
    rebinding would silently misattribute the claim to a URL its own text was
    never actually about, just via a different mechanism than the original bug)."""
    findings = ResearchFindings(
        consensus="Resistance training frequency guidance for intermediate trainees.",
        key_findings=[
            {
                "claim": "ACSM guidance lists resistance training frequency of 3-4 days per week.",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/19204579",
            }
        ],
        recommended_sources=["https://pubmed.ncbi.nlm.nih.gov/19204579"],
    )
    finalized = finalize_structured_findings(
        findings,
        # Evidence actually retrieved cites a completely different URL --
        # the claim's cited URL was only ever a search hit, never extracted.
        evidence=[
            {
                "url": "https://pubmed.ncbi.nlm.nih.gov/27102172/",
                "content": "Effects of resistance training frequency on muscle hypertrophy.",
            }
        ],
    )
    assert finalized.key_findings == []


def test_finalize_structured_findings_keeps_genuinely_evidenced_claims_and_drops_others() -> None:
    """A run with a mix of grounded and ungrounded claims: the grounded one is
    kept, the ungrounded one is dropped -- not rebound onto the grounded
    claim's URL (which filter_grounded_claims already handled correctly
    before this fix; this just confirms the mixed case still works after
    removing the whole-set rebind fallback)."""
    findings = ResearchFindings(
        consensus="Mixed grounded and ungrounded claims.",
        key_findings=[
            {
                "claim": "Grounded claim with real evidence.",
                "source_url": "https://example.edu/real",
            },
            {
                "claim": "Ungrounded claim citing an unrelated URL.",
                "source_url": "https://example.edu/unrelated",
            },
        ],
        recommended_sources=["https://example.edu/real", "https://example.edu/unrelated"],
    )
    finalized = finalize_structured_findings(
        findings,
        evidence=[{"url": "https://example.edu/real", "content": "supports the grounded claim"}],
    )
    assert len(finalized.key_findings) == 1
    assert finalized.key_findings[0].claim == "Grounded claim with real evidence."
    assert finalized.key_findings[0].source_url == "https://example.edu/real"
