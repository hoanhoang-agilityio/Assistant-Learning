"""Fitness Knowledge Store domain models and ingestion pipeline.

Persistence and retrieval live in core.repositories / core.mcp.fitness_server --
this package only owns the data model and the offline ingestion pipeline that feeds it.
"""

from core.knowledge.schema import GuidelineHit, KnowledgeChunk, KnowledgeDocument, KnowledgeSource

__all__ = ["GuidelineHit", "KnowledgeChunk", "KnowledgeDocument", "KnowledgeSource"]
