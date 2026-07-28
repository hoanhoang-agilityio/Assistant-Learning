"""Offline ingestion pipeline: Loader -> Validator -> Chunker -> Embeddings -> Repository.

Run via scripts/ingest_knowledge.py, never at request time -- see
core.knowledge.ingestion.pipeline.run_ingestion_pipeline.
"""
