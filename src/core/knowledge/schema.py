"""Schemas for the local fitness knowledge base."""

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocument(BaseModel):
    """A curated local fitness knowledge document."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=20)
    category: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    goal_applicability: list[str] = Field(default_factory=list)
    equipment_applicability: list[str] = Field(default_factory=list)
    source_type: str = Field(default="curated_note")
    source_url: str | None = None
    published_year: int | None = None
    reviewed_at: str | None = None
    trust_score: float = Field(default=0.9, ge=0.0, le=1.0)
