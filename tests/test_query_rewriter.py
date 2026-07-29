"""Unit tests for query rewrite (passthrough path -- no OpenAI)."""

import pytest

from core.knowledge.retrieval.query_rewriter import PassthroughQueryRewriter


def test_passthrough_preserves_original_and_enriches_with_profile() -> None:
    rewritten = PassthroughQueryRewriter().rewrite(
        query=" progressive overload ",
        goal="muscle_gain",
        equipment="gym",
    )
    assert rewritten.original_query == "progressive overload"
    assert rewritten.search_queries[0] == "progressive overload"
    assert "muscle_gain" in rewritten.search_queries[1]
    assert rewritten.filters.goal == "muscle_gain"
    assert rewritten.filters.equipment == "gym"


def test_passthrough_rejects_empty_query() -> None:
    with pytest.raises(ValueError):
        PassthroughQueryRewriter().rewrite(query="   ")
