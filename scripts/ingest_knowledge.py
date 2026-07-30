#!/usr/bin/env python3
"""Ingest the checked-in guideline corpus into the Fitness Knowledge Store.

Loader -> Validator -> Chunker -> EmbeddingProvider -> GuidelineRepository.upsert(...).
Writes directly to Postgres, bypassing MCP (an admin/seeding operation, not a runtime
agent action). Idempotent (ON CONFLICT DO UPDATE throughout), safe to re-run.

Requires scripts/bootstrap_fitness_db.py to have run first, and OPENAI_API_KEY set
(embeddings).
"""

from __future__ import annotations

from pathlib import Path

from core.adapters.repositories.guideline_repository import GuidelineRepository
from core.config.settings import get_settings
from core.shared.knowledge.embeddings import get_embedding_provider
from core.shared.knowledge.ingestion.chunker import SimpleChunker
from core.shared.knowledge.ingestion.loader import JSONLLoader
from core.shared.knowledge.ingestion.pipeline import run_ingestion_pipeline

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_CORPUS_PATH = _PROJECT_ROOT / "src" / "core" / "knowledge" / "data" / "corpus.jsonl"

if __name__ == "__main__":
    settings = get_settings()
    repository = GuidelineRepository(settings.checkpointer_dsn)
    try:
        stats = run_ingestion_pipeline(
            loader=JSONLLoader(_CORPUS_PATH),
            chunker=SimpleChunker(
                max_chars=settings.fitness_kb_chunk_max_chars,
                chunk_overlap=settings.fitness_kb_chunk_overlap,
            ),
            embeddings=get_embedding_provider(settings),
            repository=repository,
        )
    finally:
        repository.close()
    print(f"Ingested {stats.sources} sources, {stats.documents} documents, {stats.chunks} chunks.")
