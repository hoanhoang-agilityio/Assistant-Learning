"""Tests for knowledge-base chunking and retrieval.

Neither Postgres nor the embeddings API is touched: chunking is a pure function
over a ``.docx`` file, and the two search tests replace the embedder and the
query with fakes.

The failures these prevent are all silent ones. A chunk id that is not stable
across runs turns every re-seed into a duplicate insert, and search then returns
the same paragraph three times while a different one falls out of ``top_k``. A
split that drops the heading produces a passage that reads like advice with no
indication of which injury it is about. A search that raises instead of
degrading turns an unreachable database into a failed answer.
"""

from pathlib import Path

import pytest
from docx import Document as new_document

from app.core.configs.config import settings
from app.core.langgraph.agents.qa.tools import search_knowledge
from app.services import knowledge as knowledge_module
from app.services.knowledge import (
    MAX_CHUNK_CHARS,
    KnowledgeService,
    Passage,
    chunk_directory,
    chunk_document,
    knowledge_service,
)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"


class _FakeEmbedder:
    """Stand-in for ``OpenAIEmbeddings`` that never leaves the process."""

    def __init__(self) -> None:
        """Record the queries it was asked to embed."""
        self.queries: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        """Return a fixed vector.

        Args:
            text: The query.

        Returns:
            A one-dimensional vector — nothing downstream inspects its width,
            because the nearest-neighbour lookup is faked too.
        """
        self.queries.append(text)
        return [0.1]


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> KnowledgeService:
    """A knowledge service wired to a fake embedder."""
    instance = KnowledgeService()
    monkeypatch.setattr(instance, "_get_embedder", lambda: _FakeEmbedder())
    return instance


def _chunk(text: str) -> object:
    """Build the minimal object ``_nearest`` returns as its first element.

    Args:
        text: Passage body.

    Returns:
        An object with the ``text`` and ``source`` attributes ``search`` reads.
    """
    return type("Row", (), {"text": text, "source": "Test Doc"})()


# --- chunking a document ----------------------------------------------------


def test_section_becomes_one_chunk_carrying_its_heading(tmp_path: Path) -> None:
    """A Heading 2 section is one passage, and the heading is inside the text.

    Without the heading in the body, "Adequate hydration supports performance"
    embeds as a sentence about nothing in particular, and a question naming the
    topic does not retrieve it.
    """
    document = new_document()
    document.add_heading("Test Knowledge Base", level=1)
    document.add_heading("Hydration", level=2)
    document.add_paragraph("Drink water across the day.")
    path = tmp_path / "kb.docx"
    document.save(path)

    chunks = chunk_document(path)

    assert len(chunks) == 1
    assert chunks[0].heading == "Hydration"
    assert chunks[0].text.startswith("Hydration")
    assert "Drink water across the day." in chunks[0].text
    assert chunks[0].source == "Test Knowledge Base"


def test_heading_without_body_is_dropped(tmp_path: Path) -> None:
    """An empty section is not a passage.

    Embedding a bare heading produces a chunk that matches queries about the
    topic and then tells the reader nothing — worse than returning less.
    """
    document = new_document()
    document.add_heading("Test Knowledge Base", level=1)
    document.add_heading("Placeholder", level=2)
    document.add_heading("Recovery", level=2)
    document.add_paragraph("Sleep is the largest lever.")
    path = tmp_path / "kb.docx"
    document.save(path)

    chunks = chunk_document(path)

    assert [chunk.heading for chunk in chunks] == ["Recovery"]


def test_long_section_splits_with_the_heading_on_every_part(tmp_path: Path) -> None:
    """Each part of a split section stands on its own.

    A part retrieved without its heading loses the only thing that says which
    injury the advice belongs to.
    """
    document = new_document()
    document.add_heading("Test Knowledge Base", level=1)
    document.add_heading("Shoulder Pain", level=2)
    document.add_paragraph("Avoid painful overhead pressing. " * 200)
    path = tmp_path / "kb.docx"
    document.save(path)

    chunks = chunk_document(path)

    assert len(chunks) > 1
    assert all(chunk.text.startswith("Shoulder Pain") for chunk in chunks)
    assert all(chunk.id.startswith("kb#shoulder-pain") for chunk in chunks)
    assert len({chunk.id for chunk in chunks}) == len(chunks)


def test_repeated_heading_does_not_collide(tmp_path: Path) -> None:
    """Two sections sharing a heading keep separate ids.

    They share a primary key otherwise, and the seeder's upsert would overwrite
    the first passage with the second — losing content with no error anywhere.
    """
    document = new_document()
    document.add_heading("Test Knowledge Base", level=1)
    document.add_heading("Protein", level=2)
    document.add_paragraph("Aim for 1.6 to 2.2 g per kg.")
    document.add_heading("Protein", level=2)
    document.add_paragraph("Spread intake across meals.")
    path = tmp_path / "kb.docx"
    document.save(path)

    chunks = chunk_document(path)

    assert len({chunk.id for chunk in chunks}) == 2


def test_title_falls_back_to_the_file_name(tmp_path: Path) -> None:
    """A document with no title still cites a readable source."""
    document = new_document()
    document.add_heading("Warm-up", level=2)
    document.add_paragraph("Raise tissue temperature first.")
    path = tmp_path / "Fitness_Training_Notes.docx"
    document.save(path)

    assert chunk_document(path)[0].source == "Fitness Training Notes"


# --- chunking the documents that actually ship ------------------------------


shipped = pytest.mark.skipif(
    not _KNOWLEDGE_DIR.is_dir() or not any(_KNOWLEDGE_DIR.glob("*.docx")),
    reason="data/knowledge/*.docx is missing — the knowledge fixture needs it",
)


@pytest.fixture(scope="module")
def shipped_chunks() -> list:
    """Every passage the shipped documents currently produce."""
    return chunk_directory(_KNOWLEDGE_DIR)


@shipped
def test_shipped_documents_produce_usable_passages(shipped_chunks: list) -> None:
    """No passage is empty, unheaded, or too long to embed sensibly."""
    assert shipped_chunks

    for chunk in shipped_chunks:
        assert chunk.text.strip()
        assert chunk.heading
        assert chunk.source
        assert "_" not in chunk.source
        # The heading is prefixed to every part, so a chunk may exceed the split
        # size by that much and no more.
        assert len(chunk.text) <= MAX_CHUNK_CHARS + len(chunk.heading) + 2


@shipped
def test_chunk_ids_are_unique_and_stable(shipped_chunks: list) -> None:
    """Re-chunking unchanged documents yields the same ids and hashes.

    This is what makes the seeder an upsert rather than an append: unstable ids
    would duplicate the whole knowledge base on every run.
    """
    ids = [chunk.id for chunk in shipped_chunks]
    assert len(ids) == len(set(ids))

    again = chunk_directory(_KNOWLEDGE_DIR)
    assert [chunk.id for chunk in again] == ids
    assert [chunk.content_hash for chunk in again] == [
        chunk.content_hash for chunk in shipped_chunks
    ]


# --- search -----------------------------------------------------------------


async def test_search_maps_distance_to_score_and_applies_the_floor(
    service: KnowledgeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cosine distance becomes similarity, and weak matches are dropped.

    Nearest-neighbour search always returns its ``top_k``. Without the floor, a
    question the base does not cover comes back with the least unrelated
    paragraph in the corpus, which the model then cites as a source.
    """
    floor = settings.KNOWLEDGE_MIN_SCORE
    monkeypatch.setattr(
        knowledge_module,
        "_nearest",
        lambda vector, limit: [
            (_chunk("close"), 0.9),
            (_chunk("far"), floor - 0.01),
        ],
    )

    passages = await service.search("how much protein")

    assert [passage.text for passage in passages] == ["close"]
    assert passages[0].score == pytest.approx(0.9)


async def test_search_returns_nothing_when_the_lookup_fails(
    service: KnowledgeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database failure costs a citation, not the answer."""

    def explode(vector: list[float], limit: int) -> list:
        raise RuntimeError("pgvector is unreachable")

    monkeypatch.setattr(knowledge_module, "_nearest", explode)

    assert await service.search("how much protein") == []


async def test_search_without_an_embedder_is_empty_not_an_error() -> None:
    """An unconfigured deployment degrades instead of raising."""
    instance = KnowledgeService()
    instance._unavailable = True

    assert await instance.search("anything") == []


async def test_embed_texts_refuses_to_seed_without_an_embedder() -> None:
    """Seeding fails loudly, unlike search.

    A seeder that shrugged off a missing API key would write a knowledge base
    with holes in it, and the holes would only show up as answers that quietly
    lack a source.
    """
    instance = KnowledgeService()
    instance._unavailable = True

    with pytest.raises(RuntimeError):
        await instance.embed_texts(["something"])


# --- the tool the model calls -----------------------------------------------


async def test_tool_returns_the_documented_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """`search_knowledge` returns plain dicts with text, source and score."""

    async def fake_search(query: str, top_k: int | None = None) -> list[Passage]:
        return [Passage(text="Protein\n\nAim for 1.6 g/kg.", source="Nutrition", score=0.72)]

    monkeypatch.setattr(knowledge_service, "search", fake_search)

    result = await search_knowledge.ainvoke({"query": "protein", "top_k": 2})

    assert result == [
        {"text": "Protein\n\nAim for 1.6 g/kg.", "source": "Nutrition", "score": 0.72}
    ]


async def test_tool_reports_an_empty_base_as_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stub's contract survives: nothing found is ``[]``, never an error."""

    async def fake_search(query: str, top_k: int | None = None) -> list[Passage]:
        return []

    monkeypatch.setattr(knowledge_service, "search", fake_search)

    assert await search_knowledge.ainvoke({"query": "how do i fix my car"}) == []
