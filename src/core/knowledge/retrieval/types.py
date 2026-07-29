"""Shared types for the retrieval pipeline (rewrite → hybrid → rerank)."""

from pydantic import BaseModel, ConfigDict, Field


class MetadataFilters(BaseModel):
    """Optional document-level filters extracted or supplied for hybrid search."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = None
    equipment: str | None = None
    category: str | None = None
    topics: list[str] = Field(default_factory=list)


class RewrittenQuery(BaseModel):
    """Query-understanding output: original query preserved plus optimized variants.

    ``search_queries`` always includes the original (or an enriched original) and
    may include LLM-rewritten variants for denser / lexical recall.
    """

    model_config = ConfigDict(extra="forbid")

    original_query: str = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1)
    filters: MetadataFilters = Field(default_factory=MetadataFilters)
