"""L1 Phase 4, priority #3: deterministic relevance-based evidence compression
(core.capabilities.research.compression), replacing blind first-N-docs /
first-N-chars truncation. Pure functions -- no LLM calls, no real API cost."""

from core.capabilities.research.compression import compress_content, query_terms, score_content


class TestQueryTerms:
    def test_lowercases_and_drops_short_and_stopwords(self) -> None:
        terms = query_terms("How do I build a 4-day Hypertrophy Plan?")
        assert "hypertrophy" in terms
        assert "plan" in terms
        assert "build" in terms
        assert "how" not in terms
        assert "a" not in terms
        assert "do" not in terms

    def test_empty_query_yields_empty_terms(self) -> None:
        assert query_terms("") == frozenset()


class TestScoreContent:
    def test_numeric_sentence_scores_higher_than_prose(self) -> None:
        numeric = "Consume 1.6-2.2g of protein per kg of bodyweight daily."
        prose = "Protein is an important part of a balanced diet in general."
        assert score_content(numeric) > score_content(prose)

    def test_query_term_overlap_increases_score(self) -> None:
        terms = query_terms("hypertrophy training volume")
        on_topic = "Hypertrophy training volume of 10-20 sets per week is common."
        off_topic = "The weather today is sunny with a light breeze."
        assert score_content(on_topic, terms) > score_content(off_topic, terms)

    def test_empty_content_scores_zero(self) -> None:
        assert score_content("") == 0.0


class TestCompressContent:
    def test_short_content_passes_through_unchanged(self) -> None:
        content = "Short content well within budget."
        assert compress_content(content, max_chars=200) == content

    def test_long_content_is_compressed_within_budget(self) -> None:
        content = " ".join(f"Filler sentence number {i} with no useful data." for i in range(30))
        result = compress_content(content, max_chars=100)
        assert len(result) <= 100

    def test_keeps_the_numeric_load_bearing_sentence_over_boilerplate(self) -> None:
        """The exact failure mode this replaces: a specific, citable number
        buried after a lot of boilerplate must survive truncation instead of
        being cut away by a blind prefix slice."""
        boilerplate = "Welcome to our website. Please accept cookies. Subscribe to our newsletter. "
        load_bearing = (
            "Position-stand guidance recommends 1.6-2.2g of protein per kg bodyweight daily."
        )
        trailer = "Thanks for reading. Visit again soon. Follow us on social media."
        content = boilerplate * 3 + load_bearing + " " + trailer * 3

        blind_prefix = content[:120]
        assert "1.6-2.2g" not in blind_prefix  # confirms the old behavior really did lose it

        compressed = compress_content(content, max_chars=120)
        assert "1.6-2.2g" in compressed

    def test_prioritizes_query_relevant_sentences_when_content_exceeds_budget(self) -> None:
        terms = query_terms("hypertrophy training frequency")
        content = (
            "Unrelated commentary about market trends fills this first sentence. "
            "Training each muscle group twice per week improves hypertrophy outcomes. "
            "More unrelated commentary about unrelated topics follows here too."
        )
        compressed = compress_content(content, max_chars=90, terms=terms)
        assert "hypertrophy" in compressed.lower()

    def test_falls_back_to_prefix_slice_when_no_sentence_punctuation(self) -> None:
        content = "x" * 500
        assert compress_content(content, max_chars=50) == content[:50]

    def test_falls_back_to_prefix_slice_when_no_chunk_fits(self) -> None:
        # A single sentence far longer than the budget -- no chunk can fit,
        # so the safety-net prefix slice applies (never worse than before).
        content = "This one very long unbroken sentence has no stops in it at all so it keeps going"
        result = compress_content(content, max_chars=20)
        assert result == content[:20]
