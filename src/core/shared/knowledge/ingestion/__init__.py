"""Offline ingestion pipeline: Loader -> Validator -> Chunker -> Embeddings -> Repository.

Run via scripts/ingest_knowledge.py, never at request time -- see
core.shared.knowledge.ingestion.pipeline.run_ingestion_pipeline.
"""
