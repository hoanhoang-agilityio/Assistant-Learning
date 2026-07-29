"""Fitness Knowledge Store domain models, ingestion, and retrieval pipeline.

Persistence lives in core.repositories; the Fitness MCP Server exposes tools.
This package owns the data model, offline ingestion, and the retrieval pipeline
(query rewrite → hybrid → rerank) orchestrated by RetrievalService.
"""

from core.knowledge.schema import GuidelineHit, KnowledgeChunk, KnowledgeDocument, KnowledgeSource

__all__ = ["GuidelineHit", "KnowledgeChunk", "KnowledgeDocument", "KnowledgeSource"]
