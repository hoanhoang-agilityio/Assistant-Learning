"""Tests for the ``search_knowledge`` tool and the pgvector retrieval behind it."""

import json
import sys

import pytest

from src.core.configs.config import settings
from src.core.langgraph.tools import QA_TOOLS, search_knowledge
from src.core.langgraph.tools.search_knowledge import NO_PASSAGES
from src.models import KnowledgeChunk
from src.services import knowledge

tool_module = sys.modules[search_knowledge.coroutine.__module__]

PROTEIN = "Protein\n\nAim for 1.6 to 2.2 g per kg of bodyweight per day."
HYDRATION = "Hydration\n\nDrink to thirst, and add electrolytes on long sessions."
QUESTION = "how much protein do I need?"


def _chunk(text: str, source: str = "Sports Nutrition") -> KnowledgeChunk:
    """A stored passage, as the table hands it back."""
    return KnowledgeChunk(
        id=f"nutrition#{len(text)}",
        source=source,
        heading=text.split("\n", maxsplit=1)[0],
        chunk_index=0,
        text=text,
        content_hash="hash",
        embedding=[0.0] * settings.KNOWLEDGE_EMBEDDING_DIM,
    )


class _Embedder:
    """An embedding client that answers without a network call, and records what it embedded."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1] * settings.KNOWLEDGE_EMBEDDING_DIM


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> _Embedder:
    """No test in this file reaches OpenAI."""
    client = _Embedder()
    monkeypatch.setattr(knowledge, "embedder", lambda: client)
    return client


@pytest.fixture
def nearest(monkeypatch: pytest.MonkeyPatch):
    """Stand in for the pgvector query, recording the limit it was asked for."""

    def _stub(*rows: tuple[KnowledgeChunk, float]):
        calls: list[int] = []

        async def _nearest(vector: list[float], limit: int):
            calls.append(limit)
            return list(rows)

        monkeypatch.setattr(knowledge, "_nearest", _nearest)
        return calls

    return _stub


# --- Retrieval ---------------------------------------------------------------------------


async def test_a_passage_comes_back_in_the_shape_the_spec_fixes(
    embedder, nearest
) -> None:
    """`{text, source, score}` is what the answer cites and what RAGAS is handed."""
    nearest((_chunk(PROTEIN), 0.87))

    assert await knowledge.search(QUESTION) == [
        {"text": PROTEIN, "source": "Sports Nutrition", "score": 0.87}
    ]


async def test_the_question_itself_is_what_gets_embedded(embedder, nearest) -> None:
    """Retrieval is by meaning: the query embedding has to be of the user's own words."""
    nearest()

    await knowledge.search(QUESTION)

    assert embedder.queries == [QUESTION]


async def test_the_configured_top_k_is_what_reaches_the_agent(
    embedder, nearest
) -> None:
    """`top_k` is a tuned retrieval setting, so it comes from config and not from a caller."""
    nearest(
        *((_chunk(f"Section {index}\n\nDistinct prose."), 0.9) for index in range(20))
    )

    assert len(await knowledge.search(QUESTION)) == settings.KNOWLEDGE_TOP_K == 4


async def test_more_candidates_are_fetched_than_are_returned(embedder, nearest) -> None:
    """The threshold and the duplicate filter both remove rows; filtering exactly `top_k` of
    them would let one near-duplicate cost the agent a passage it could have had."""
    calls = nearest()

    await knowledge.search(QUESTION)

    assert calls == [settings.KNOWLEDGE_TOP_K * knowledge.CANDIDATE_MULTIPLIER]


async def test_a_caller_may_still_widen_the_search(embedder, nearest) -> None:
    """The evaluation harness sweeps `top_k` to tune the threshold; the default is not a ceiling."""
    calls = nearest()

    await knowledge.search(QUESTION, top_k=10)

    assert calls == [10 * knowledge.CANDIDATE_MULTIPLIER]


# --- The similarity threshold ------------------------------------------------------------


async def test_a_passage_below_the_threshold_is_not_an_answer(
    embedder, nearest
) -> None:
    """pgvector returns the nearest rows whether or not any of them is close; the floor decides."""
    nearest((_chunk(PROTEIN), 0.9), (_chunk(HYDRATION), 0.05))

    assert [passage["text"] for passage in await knowledge.search(QUESTION)] == [
        PROTEIN
    ]


async def test_nothing_close_enough_retrieves_nothing(embedder, nearest) -> None:
    """The spec's answer to an unanswerable question is `[]`, which the QA prompt handles."""
    nearest((_chunk(PROTEIN), 0.1), (_chunk(HYDRATION), 0.05))

    assert await knowledge.search(QUESTION) == []


async def test_the_threshold_itself_still_counts_as_relevant(
    embedder, nearest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tuned threshold is the lowest score worth answering from, not the first one dropped."""
    monkeypatch.setattr(settings, "KNOWLEDGE_MIN_SCORE", 0.5)
    nearest((_chunk(PROTEIN), 0.5))

    assert len(await knowledge.search(QUESTION)) == 1


# --- Duplicate and overlapping passages --------------------------------------------------


async def test_the_same_passage_in_two_documents_is_carried_once(
    embedder, nearest
) -> None:
    """Two copies of one claim weight it twice in the answer and cost a passage of `top_k`."""
    nearest(
        (_chunk(PROTEIN, source="Sports Nutrition"), 0.91),
        (_chunk(PROTEIN, source="Training Guide"), 0.88),
        (_chunk(HYDRATION), 0.7),
    )

    assert await knowledge.search(QUESTION) == [
        {"text": PROTEIN, "source": "Sports Nutrition", "score": 0.91},
        {"text": HYDRATION, "source": "Sports Nutrition", "score": 0.7},
    ]


async def test_a_near_duplicate_is_dropped_and_the_closer_one_kept(
    embedder, nearest
) -> None:
    """Rows arrive closest-first, so the copy that survives is the better match."""
    padded = f"{PROTEIN} Prioritise it after training."
    nearest(
        (_chunk(PROTEIN, source="Sports Nutrition"), 0.91),
        (_chunk(padded, source="Training Guide"), 0.88),
    )

    assert await knowledge.search(QUESTION) == [
        {"text": PROTEIN, "source": "Sports Nutrition", "score": 0.91}
    ]


async def test_two_passages_on_one_topic_are_two_answers(embedder, nearest) -> None:
    """Over-eager de-duplication is indistinguishable from a knowledge base with holes."""
    timing = "Protein timing\n\nSpread it across three or four meals through the day."
    nearest((_chunk(PROTEIN), 0.91), (_chunk(timing), 0.85))

    assert len(await knowledge.search(QUESTION)) == 2


async def test_adjacent_parts_of_one_long_section_both_survive(
    embedder, nearest
) -> None:
    """`_split_long` repeats 150 characters at the seam; that is a seam, not a duplicate."""
    section = " ".join(
        f"Rule {index} covers one aspect of weekly training volume."
        for index in range(120)
    )
    parts = knowledge._split_long(section)
    nearest(*((_chunk(f"Volume\n\n{part}"), 0.9) for part in parts))

    assert len(parts) > 1
    assert len(await knowledge.search(QUESTION, top_k=len(parts))) == len(parts)


def test_overlap_is_symmetric_and_bounded() -> None:
    """A one-sided or unbounded measure cannot be compared against a tuned threshold."""
    assert knowledge.overlap(PROTEIN, PROTEIN) == 1.0
    assert knowledge.overlap(PROTEIN, HYDRATION) == knowledge.overlap(
        HYDRATION, PROTEIN
    )
    assert knowledge.overlap("", "") == 0.0


async def test_ranking_is_left_to_pgvector(embedder, nearest) -> None:
    """The index orders by distance; re-sorting in Python would only be able to agree."""
    nearest((_chunk(PROTEIN), 0.9), (_chunk(HYDRATION), 0.4))

    assert [passage["text"] for passage in await knowledge.search(QUESTION)] == [
        PROTEIN,
        HYDRATION,
    ]


async def test_an_empty_question_costs_no_embedding_call(embedder, nearest) -> None:
    """There is nothing to be near, and the call would still be billed."""
    nearest((_chunk(PROTEIN), 0.9))

    assert await knowledge.search("   ") == []
    assert embedder.queries == []


async def test_a_retrieval_failure_costs_the_citation_and_not_the_answer(
    monkeypatch: pytest.MonkeyPatch, embedder
) -> None:
    """The QA prompt already handles an empty result; a raise here would fail the whole turn."""

    async def _explode(vector: list[float], limit: int):
        raise RuntimeError("pgvector unavailable")

    monkeypatch.setattr(knowledge, "_nearest", _explode)

    assert await knowledge.search(QUESTION) == []


async def test_an_embedding_failure_degrades_the_same_way(
    monkeypatch: pytest.MonkeyPatch, nearest
) -> None:
    """Retrieval has two halves and only one error path."""

    class _Broken:
        async def aembed_query(self, text: str) -> list[float]:
            raise RuntimeError("openai unavailable")

    monkeypatch.setattr(knowledge, "embedder", _Broken)
    nearest()

    assert await knowledge.search(QUESTION) == []


# --- The tool ----------------------------------------------------------------------------


def test_the_tool_is_bound_to_the_qa_agent() -> None:
    """A retrieval tool the model cannot reach is a QA agent answering from memory."""
    assert search_knowledge in QA_TOOLS


def test_the_model_cannot_set_top_k() -> None:
    """It is a tuned setting; a model that can widen it can also spend the context window."""
    assert set(search_knowledge.args) == {"query"}


async def _invoke(query: str) -> tuple[str, list[dict]]:
    """Run the tool the way the agent's tool node does, keeping the artifact."""
    message = await search_knowledge.ainvoke(
        {
            "type": "tool_call",
            "id": "1",
            "name": "search_knowledge",
            "args": {"query": query},
        }
    )
    return message.content, message.artifact


async def test_the_tool_hands_the_model_the_passages_it_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the model reads and what the gate scores must be the same passages."""
    passages = [{"text": PROTEIN, "source": "Sports Nutrition", "score": 0.9}]

    async def _search(query: str):
        return passages

    monkeypatch.setattr(tool_module, "search", _search)
    content, artifact = await _invoke(QUESTION)

    assert json.loads(content) == passages
    assert artifact == passages


async def test_an_empty_result_is_told_to_the_model_in_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[]` serialized as JSON reads as a tool that failed, not as a base with no material."""

    async def _search(query: str):
        return []

    monkeypatch.setattr(tool_module, "search", _search)
    content, artifact = await _invoke(QUESTION)

    assert content == NO_PASSAGES
    assert artifact == []
