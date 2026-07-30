"""L1 Phase 4, priority #4: topical relevance must gate `verified` regardless
of domain tier, ranking must penalize off-topic sources, and Tavily-side
include_domains scoping must only apply when research_trusted_domains is
explicitly configured. Root cause: a real run's evidence included an
unrelated materials-science paper -- domain trust (.edu/.gov/whitelist) was
being treated as sufficient on its own, with topical relevance only ever
consulted as a fallback for sources that failed every domain check. No real
API calls -- Tavily client is faked/monkeypatched throughout."""

from typing import Any

import pytest

from core.config.settings import Settings
from core.subgraphs.research.ranking import compute_composite_score
from core.subgraphs.research.utils import search_tavily_data
from core.subgraphs.research.verification import (
    has_explicit_trusted_domains,
    verify_source,
    verify_sources_data,
)


class TestVerifySourceTopicalRelevanceGate:
    """`topically_relevant` is a new, always-computed signal that ranking.py
    uses to demote (not exclude) off-topic sources -- it deliberately does
    NOT gate `verified` itself (see verify_source's docstring for why: the
    8-keyword relevance check is too blunt to trust as a hard gate on
    something that feeds a "skip further searching" shortcut)."""

    def test_whitelisted_domain_off_topic_source_is_flagged_not_relevant(self) -> None:
        """The exact confirmed bug's raw material: a prestigious/whitelisted
        domain hosting content with zero fitness relevance. `verified` stays
        True (domain trust, unchanged meaning) -- ranking.py's penalty is
        what actually keeps this out of the top-K extracted into evidence."""
        source = {
            "title": "Chiral Lead-Free Double Perovskite Second-Harmonic Generation",
            "url": "https://pubmed.ncbi.nlm.nih.gov/materials-science-paper",
            "snippet": "A study of nonlinear optical properties in perovskite crystals.",
        }
        result = verify_source(source)
        assert result["authority_tier"] == "whitelist"
        assert result["topically_relevant"] is False
        assert result["verified"] is True

    def test_government_edu_off_topic_source_is_flagged_not_relevant(self) -> None:
        source = {
            "title": "Department of Agricultural Economics Annual Report",
            "url": "https://example.edu/agri-econ-report",
            "snippet": "Crop yield forecasting models for the coming fiscal year.",
        }
        result = verify_source(source)
        assert result["authority_tier"] == "government_edu"
        assert result["topically_relevant"] is False

    def test_whitelisted_domain_on_topic_source_is_relevant_and_verified(self) -> None:
        """The fix must not regress the normal, intended case."""
        source = {
            "title": "Resistance training and hypertrophy: a systematic review",
            "url": "https://pubmed.ncbi.nlm.nih.gov/real-fitness-study",
            "snippet": "Training volume and muscle hypertrophy outcomes.",
        }
        result = verify_source(source)
        assert result["topically_relevant"] is True
        assert result["verified"] is True

    def test_whitelisted_domain_with_generic_metadata_stays_verified(self) -> None:
        """Regression: a genuinely relevant source whose title/snippet just
        doesn't happen to contain one of the 8 keywords (e.g. Tavily's own
        generic result title) must not lose `verified` and get treated as
        insufficient coverage -- that's a real false-negative risk of the
        keyword heuristic, which is why it's a ranking demotion, not a gate."""
        source = {
            "title": "PubMed review",
            "url": "https://pubmed.ncbi.nlm.nih.gov/study",
            "snippet": "systematic review",
        }
        result = verify_source(source)
        assert result["topically_relevant"] is False
        assert result["verified"] is True

    def test_unverified_domain_with_fitness_keywords_is_still_verified(self) -> None:
        source = {
            "title": "Training blog",
            "url": "https://example.com/training",
            "snippet": "hypertrophy workout guidance",
        }
        result = verify_source(source)
        assert result["authority_tier"] == "fitness_keyword"
        assert result["verified"] is True

    def test_verify_sources_data_annotates_every_source_with_topically_relevant(self) -> None:
        sources = [
            {"title": "Off-topic", "url": "https://nih.gov/other", "snippet": "unrelated physics"},
        ]
        result = verify_sources_data(sources)
        assert "topically_relevant" in result["sources"][0]


class TestRankingOffTopicPenalty:
    def test_off_topic_source_ranks_below_an_otherwise_similar_on_topic_source(self) -> None:
        base = {"score": 0.9, "authority_score": 1.0, "title": "", "snippet": ""}
        on_topic = {**base, "topically_relevant": True}
        off_topic = {**base, "topically_relevant": False}
        assert compute_composite_score(off_topic) < compute_composite_score(on_topic)

    def test_missing_topically_relevant_key_defaults_to_no_penalty(self) -> None:
        """Sources built directly in a test/ad-hoc context (never run through
        verify_source) must not be silently penalized."""
        with_key = {"score": 0.5, "authority_score": 0.5, "topically_relevant": True}
        without_key = {"score": 0.5, "authority_score": 0.5}
        assert compute_composite_score(with_key) == compute_composite_score(without_key)


class TestHasExplicitTrustedDomains:
    def test_false_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "core.subgraphs.research.verification.get_settings",
            lambda: Settings(research_trusted_domains=""),
        )
        assert has_explicit_trusted_domains() is False

    def test_true_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "core.subgraphs.research.verification.get_settings",
            lambda: Settings(research_trusted_domains="example.edu"),
        )
        assert has_explicit_trusted_domains() is True


class TestSearchTavilyDataIncludeDomainsThreading:
    def test_does_not_pass_include_domains_under_default_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_search(query: str, include_domains: list[str] | None = None) -> dict[str, Any]:
            captured["include_domains"] = include_domains
            return {"results": []}

        monkeypatch.setattr(
            "core.subgraphs.research.utils.get_tavily_client",
            lambda: type("_C", (), {"search": staticmethod(fake_search)})(),
        )
        monkeypatch.setattr(
            "core.subgraphs.research.utils.get_cached_search_result", lambda query: None
        )
        monkeypatch.setattr("core.subgraphs.research.utils.store_search_result", lambda *a: None)
        monkeypatch.setattr(
            "core.subgraphs.research.utils.has_explicit_trusted_domains", lambda: False
        )

        search_tavily_data("progressive overload training volume")

        assert captured["include_domains"] is None

    def test_passes_resolved_trusted_domains_when_explicitly_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_search(query: str, include_domains: list[str] | None = None) -> dict[str, Any]:
            captured["include_domains"] = include_domains
            return {"results": []}

        monkeypatch.setattr(
            "core.subgraphs.research.utils.get_tavily_client",
            lambda: type("_C", (), {"search": staticmethod(fake_search)})(),
        )
        monkeypatch.setattr(
            "core.subgraphs.research.utils.get_cached_search_result", lambda query: None
        )
        monkeypatch.setattr("core.subgraphs.research.utils.store_search_result", lambda *a: None)
        monkeypatch.setattr(
            "core.subgraphs.research.utils.has_explicit_trusted_domains", lambda: True
        )
        monkeypatch.setattr(
            "core.subgraphs.research.utils.resolve_trusted_domains",
            lambda: ("example.edu", "example.org"),
        )

        search_tavily_data("progressive overload training volume")

        assert captured["include_domains"] == ["example.edu", "example.org"]
