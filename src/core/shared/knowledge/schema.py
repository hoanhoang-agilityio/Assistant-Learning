"""Domain models for the Fitness Knowledge Store.

Storage-side models (KnowledgeSource/KnowledgeDocument/KnowledgeChunk) mirror the
Postgres schema in core.adapters.repositories.bootstrap. GuidelineHit is the retrieval-result
shape returned by the Fitness MCP Server's search_guidelines tool -- a denormalized
join of chunk + document + source for callers that think in terms of "a matched piece
of knowledge", not raw storage rows.
"""

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSource(BaseModel):
    """Provenance: where a document came from."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str | None = None
    url: str | None = None
    published_year: int | None = None
    reviewed_at: str | None = None
    license: str | None = None
    source_type: str = Field(default="curated_note")
    trust_score: float = Field(default=0.9, ge=0.0, le=1.0)


class KnowledgeDocument(BaseModel):
    """A logical document within a source (today: 1:1 with the source for seed data)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    kind: str = Field(default="guideline")  # extension seam: "exercise", "food", ... later
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    goal_applicability: list[str] = Field(default_factory=list)
    equipment_applicability: list[str] = Field(default_factory=list)


class KnowledgeChunk(BaseModel):
    """One embeddable unit of a document's content."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)


class GuidelineHit(BaseModel):
    """Retrieval-result shape returned by search_guidelines -- a denormalized join of
    chunk + document + source, reconstituted for callers that think in terms of 'a
    matched piece of knowledge', not raw storage rows."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    chunk_id: str
    title: str
    content: str
    category: str
    tags: list[str] = Field(default_factory=list)
    goal_applicability: list[str] = Field(default_factory=list)
    equipment_applicability: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_type: str = Field(default="curated_note")
    trust_score: float = Field(default=0.9, ge=0.0, le=1.0)
    similarity: float
