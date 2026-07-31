"""Orchestrates Loader -> Validator -> Chunker -> Embeddings -> Repository.upsert(...).

Reusable/testable independent of both the CLI script and Postgres: loader/chunker are
protocols, embeddings/repository are passed in -- see scripts/ingest_knowledge.py for
the real wiring and tests/test_knowledge_ingestion_pipeline.py for fakes.
"""

from dataclasses import dataclass, replace

from langchain_core.embeddings import Embeddings

from core.adapters.db.guideline_repository import GuidelineRepository
from core.shared.knowledge.ingestion.chunker import Chunker
from core.shared.knowledge.ingestion.loader import Loader
from core.shared.knowledge.ingestion.validator import validate_record


@dataclass(frozen=True)
class IngestionStats:
    sources: int = 0
    documents: int = 0
    chunks: int = 0


def run_ingestion_pipeline(
    *,
    loader: Loader,
    chunker: Chunker,
    embeddings: Embeddings,
    repository: GuidelineRepository,
) -> IngestionStats:
    """Embeds all chunks for a document in one embed_documents() batch call (not one
    embed_query() call per chunk) -- matters once documents produce many chunks."""
    stats = IngestionStats()
    for record in loader.load():
        source, document, content = validate_record(record)
        chunks = chunker.chunk(document.id, content)
        vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
        repository.upsert(source, document, list(zip(chunks, vectors, strict=True)))
        stats = replace(
            stats,
            sources=stats.sources + 1,
            documents=stats.documents + 1,
            chunks=stats.chunks + len(chunks),
        )
    return stats
