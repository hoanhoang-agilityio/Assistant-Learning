"""Load ``data/knowledge/*.docx`` into the pgvector knowledge base.

Idempotent, and deliberately frugal with the embeddings API: a passage whose
``content_hash`` is unchanged is left alone, so re-running after editing one
paragraph re-embeds one paragraph. Passages that no longer exist in their source
document are deleted — unlike the exercise catalog, nothing stores a reference
to a chunk id, so a section removed from a document must disappear from search
rather than linger as a citation of text that is no longer in the source.

Run::

    uv run python scripts/seed_knowledge.py --dry-run   # chunk plan, no API calls
    uv run alembic upgrade head                         # create the table
    uv run python scripts/seed_knowledge.py             # embed and load

Until this has run, ``search_knowledge`` returns an empty list on every query.
That is honest — the QA prompt tells the model to answer from its own knowledge
and say the base had nothing — but it is not the intended state.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.core.logging import logger  # noqa: E402
from app.models.database import engine  # noqa: E402
from app.models.knowledge import KnowledgeChunk  # noqa: E402
from app.services.knowledge import Chunk, chunk_directory, knowledge_service  # noqa: E402

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"


class SeedReport:
    """What one seeding run changed."""

    def __init__(self) -> None:
        """Start an empty report."""
        self.inserted = 0
        self.updated = 0
        self.unchanged = 0
        self.deleted = 0

    @property
    def embedded(self) -> int:
        """How many passages were sent to the embeddings API.

        Returns:
            The count of inserted plus updated passages.
        """
        return self.inserted + self.updated

    def __str__(self) -> str:
        """Render the report for the terminal.

        Returns:
            A one-line summary.
        """
        return (
            f"{self.inserted} inserted, {self.updated} updated, "
            f"{self.unchanged} unchanged, {self.deleted} deleted"
        )


def _plan(chunks: list[Chunk]) -> tuple[list[Chunk], list[str], SeedReport]:
    """Work out which passages need embedding and which rows are stale.

    Args:
        chunks: Every passage the source documents currently produce.

    Returns:
        ``(to_embed, to_delete, report)`` — passages whose text is new or
        changed, ids no longer backed by a document, and the counts so far.
    """
    report = SeedReport()

    with Session(engine) as session:
        stored = {row.id: row.content_hash for row in session.exec(select(KnowledgeChunk)).all()}

    to_embed: list[Chunk] = []
    for chunk in chunks:
        current = stored.get(chunk.id)
        if current is None:
            report.inserted += 1
            to_embed.append(chunk)
        elif current != chunk.content_hash:
            report.updated += 1
            to_embed.append(chunk)
        else:
            report.unchanged += 1

    live_ids = {chunk.id for chunk in chunks}
    to_delete = [chunk_id for chunk_id in stored if chunk_id not in live_ids]
    report.deleted = len(to_delete)

    return to_embed, to_delete, report


def _write(chunks: list[Chunk], embeddings: list[list[float]], stale_ids: list[str]) -> None:
    """Apply the planned changes in one transaction.

    Args:
        chunks: Passages to insert or update.
        embeddings: Their vectors, in the same order.
        stale_ids: Ids to remove.
    """
    with Session(engine) as session:
        existing = {row.id: row for row in session.exec(select(KnowledgeChunk)).all()}

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            row = existing.get(chunk.id)
            if row is None:
                session.add(KnowledgeChunk(**chunk.model_dump(), embedding=embedding))
                continue

            row.source = chunk.source
            row.heading = chunk.heading
            row.chunk_index = chunk.chunk_index
            row.text = chunk.text
            row.content_hash = chunk.content_hash
            row.embedding = embedding
            session.add(row)

        for chunk_id in stale_ids:
            row = existing.get(chunk_id)
            if row is not None:
                session.delete(row)

        session.commit()


async def seed(dry_run: bool = False) -> int:
    """Chunk the documents, embed what changed and write it.

    Args:
        dry_run: Print the chunk plan and stop, without calling the embeddings
            API or touching the database.

    Returns:
        Process exit code: 0 on success, 1 when the knowledge folder is missing
        or holds no documents.
    """
    if not _KNOWLEDGE_DIR.is_dir():
        print(
            f"missing {_KNOWLEDGE_DIR}. "
            "The .docx files in it are the source of truth for the knowledge base.",
            file=sys.stderr,
        )
        return 1

    chunks = chunk_directory(_KNOWLEDGE_DIR)
    if not chunks:
        print(f"no .docx documents found in {_KNOWLEDGE_DIR}", file=sys.stderr)
        return 1

    if dry_run:
        for chunk in chunks:
            print(f"{chunk.id:<60} {len(chunk.text):>5} chars  {chunk.source} / {chunk.heading}")
        print(f"\n{len(chunks)} passages from {_KNOWLEDGE_DIR} (dry run, nothing written)")
        return 0

    to_embed, to_delete, report = _plan(chunks)

    embeddings = await knowledge_service.embed_texts([chunk.text for chunk in to_embed])
    _write(to_embed, embeddings, to_delete)

    logger.info(
        "knowledge_seeded",
        total=len(chunks),
        inserted=report.inserted,
        updated=report.updated,
        unchanged=report.unchanged,
        deleted=report.deleted,
    )
    print(f"knowledge base: {len(chunks)} passages — {report} ({report.embedded} embedded)")
    return 0


def main() -> int:
    """Parse arguments and run the seeder.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the passages that would be stored, without embedding or writing",
    )
    args = parser.parse_args()
    return asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
