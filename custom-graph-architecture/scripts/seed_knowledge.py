"""Embed the knowledge documents in ``data/knowledge/`` and load them into Postgres.

    uv run python scripts/seed_knowledge.py
"""

import asyncio
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from src.models.knowledge import KnowledgeChunk
from src.services.database import close_engine, session_factory
from src.services.knowledge import Chunk, chunk_directory, embed_chunks
from src.utils.logging import logger


async def _stored_hashes() -> dict[str, str]:
    """The fingerprint of every passage already in the table."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(KnowledgeChunk.id, KnowledgeChunk.content_hash)
            )
        ).all()

    return {chunk_id: content_hash for chunk_id, content_hash in rows}


async def _upsert(rows: list[dict[str, Any]]) -> None:
    """Insert the embedded passages, replacing any already there."""
    if not rows:
        return

    statement = insert(KnowledgeChunk)
    statement = statement.on_conflict_do_update(
        index_elements=["id"],
        set_={key: statement.excluded[key] for key in rows[0] if key != "id"},
    )
    async with session_factory() as session:
        await session.execute(statement, rows)
        await session.commit()


async def _refresh(chunks: list[Chunk]) -> None:
    """Bring an unchanged passage's citation and position up to date, leaving its vector alone."""

    if not chunks:
        return

    async with session_factory() as session:
        await session.execute(
            update(KnowledgeChunk),
            [
                {
                    "id": chunk.id,
                    "source": chunk.source,
                    "heading": chunk.heading,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ],
        )
        await session.commit()


async def _prune(chunks: list[Chunk]) -> int:
    """Delete the passages the documents no longer carry. """

    async with session_factory() as session:
        result = await session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.id.notin_([chunk.id for chunk in chunks])
            )
        )
        await session.commit()

    return result.rowcount


async def main() -> None:
    """Seed the knowledge base from ``data/knowledge/``."""
    chunks = chunk_directory()
    if not chunks:
        raise SystemExit("no knowledge documents found in data/knowledge/")

    stored = await _stored_hashes()
    stale = [chunk for chunk in chunks if stored.get(
        chunk.id) != chunk.content_hash]
    unchanged = [
        chunk for chunk in chunks if stored.get(chunk.id) == chunk.content_hash
    ]

    await _upsert(await embed_chunks(stale))
    await _refresh(unchanged)
    dropped = await _prune(chunks)
    await close_engine()

    logger.info(
        "knowledge_seeded",
        passages=len(chunks),
        embedded=len(stale),
        reused=len(unchanged),
        dropped=dropped,
    )


if __name__ == "__main__":
    asyncio.run(main())
