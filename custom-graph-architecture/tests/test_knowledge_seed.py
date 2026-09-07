"""Tests for the seeded knowledge base.

The seeder's two halves fail differently: embedding is a cost, and the metadata refresh is
a silent no-op until a document is edited. The unit tests below drive both against a fake
table; the ``integration`` ones read what is actually stored.
"""

import pytest
from sqlmodel import func, select

import scripts.seed_knowledge as seeder
from src.configs.config import settings
from src.models.knowledge import KnowledgeChunk
from src.services.database import session_factory
from src.services.knowledge import Chunk, chunk_directory


def _chunk(chunk_id: str, text: str, *, chunk_index: int = 0) -> Chunk:
    """One passage as the chunker produces it."""
    return Chunk(
        id=chunk_id,
        source="Fitness Nutrition Knowledge Base",
        heading="Protein",
        chunk_index=chunk_index,
        text=text,
        content_hash=text,
    )


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch):
    """Run the seeder against recorded calls rather than Postgres or OpenAI."""

    def _run(chunks: list[Chunk], stored: dict[str, str]):
        calls: dict[str, list] = {"embedded": [], "upserted": [], "refreshed": []}

        async def _hashes() -> dict[str, str]:
            return stored

        async def _embed(batch: list[Chunk]) -> list[dict]:
            calls["embedded"] = list(batch)
            return [
                chunk.model_dump()
                | {"embedding": [0.1] * settings.KNOWLEDGE_EMBEDDING_DIM}
                for chunk in batch
            ]

        async def _upsert(rows: list[dict]) -> None:
            calls["upserted"] = rows

        async def _refresh(batch: list[Chunk]) -> None:
            calls["refreshed"] = list(batch)

        async def _prune(batch: list[Chunk]) -> int:
            return 0

        monkeypatch.setattr(seeder, "chunk_directory", lambda: chunks)
        monkeypatch.setattr(seeder, "_stored_hashes", _hashes)
        monkeypatch.setattr(seeder, "embed_chunks", _embed)
        monkeypatch.setattr(seeder, "_upsert", _upsert)
        monkeypatch.setattr(seeder, "_refresh", _refresh)
        monkeypatch.setattr(seeder, "_prune", _prune)
        monkeypatch.setattr(seeder, "close_engine", _noop)
        return calls

    return _run


async def _noop() -> None:
    """Stand in for disposing the engine, which these tests never opened."""


async def test_an_empty_table_embeds_every_passage(seeded) -> None:
    """The first run has nothing to reuse."""
    chunks = [_chunk("nutrition#protein", "Eat protein.")]
    calls = seeded(chunks, {})

    await seeder.main()

    assert calls["embedded"] == chunks
    assert calls["refreshed"] == []


async def test_an_unchanged_passage_is_not_embedded_again(seeded) -> None:
    """Re-seeding an untouched corpus must cost nothing; that is what the hash is for."""
    chunks = [_chunk("nutrition#protein", "Eat protein.")]
    calls = seeded(chunks, {"nutrition#protein": "Eat protein."})

    await seeder.main()

    assert calls["embedded"] == []
    assert calls["refreshed"] == chunks


async def test_only_the_edited_passage_is_paid_for(seeded) -> None:
    """A one-line edit to one document must not re-embed the corpus around it."""
    edited = _chunk("nutrition#protein", "Eat more protein.")
    untouched = _chunk("nutrition#fat", "Eat fat.", chunk_index=1)
    calls = seeded(
        [edited, untouched],
        {"nutrition#protein": "Eat protein.", "nutrition#fat": "Eat fat."},
    )

    await seeder.main()

    assert calls["embedded"] == [edited]
    assert calls["refreshed"] == [untouched]


async def test_a_run_with_no_documents_stops_rather_than_pruning(seeded) -> None:
    """An empty folder is a mistake, and pruning against it would empty the table."""
    calls = seeded([], {"nutrition#protein": "Eat protein."})

    with pytest.raises(SystemExit):
        await seeder.main()

    assert calls["upserted"] == []


# --- The table ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_every_passage_in_the_documents_is_stored(require_postgres: None) -> None:
    """Retrieval can only reach what the seeder wrote; a dropped passage is a silent hole."""
    chunks = chunk_directory()

    async with session_factory() as session:
        stored = (await session.execute(select(KnowledgeChunk.id))).scalars().all()

    assert set(stored) == {chunk.id for chunk in chunks}


@pytest.mark.integration
async def test_every_stored_passage_carries_a_full_vector(
    require_postgres: None,
) -> None:
    """A short vector cannot be compared against a query and would fail at retrieval time."""
    async with session_factory() as session:
        rows = (await session.execute(select(KnowledgeChunk).limit(5))).scalars().all()
        count = (
            await session.execute(select(func.count()).select_from(KnowledgeChunk))
        ).scalar()

    assert count > 0
    assert all(len(row.embedding) == settings.KNOWLEDGE_EMBEDDING_DIM for row in rows)
    assert all(row.text.startswith(f"{row.heading}\n\n") for row in rows)
