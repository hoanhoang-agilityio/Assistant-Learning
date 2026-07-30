"""Fitness Knowledge Store domain models, ingestion, and retrieval pipeline.

Persistence lives in core.adapters.repositories; the Fitness MCP Server exposes tools.
This package owns the data model, offline ingestion, and the retrieval pipeline
(query rewrite -> hybrid -> rerank) orchestrated by RetrievalService.

Placed under `shared/`, not `capabilities/retrieval/` as the architecture
review's Step 6 proposed. Measured before moving: it has no graph node and no
executor, so it is not a routed capability -- and its consumers span the
research capability, the Fitness MCP server, the guideline repository and the
evaluation suite. Used by several, owned by none.

Internals deliberately untouched: the QueryRewriter / HybridRetriever / Reranker
protocol set is the best-justified abstraction in this codebase.
"""

from core.shared.knowledge.schema import (
    GuidelineHit,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)

__all__ = ["GuidelineHit", "KnowledgeChunk", "KnowledgeDocument", "KnowledgeSource"]
