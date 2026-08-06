"""Knowledge base passages and their embeddings.

pgvector rather than Postgres full-text, the queries
that reach this table are questions in the user's own words — "should I train
if my shoulder hurts", "how much protein" — and the passage that answers them
rarely shares their vocabulary. Similarity is the whole point, which is the
opposite of the exercise catalog next door, where every query is an exact set
operation and a vector store would be the wrong answer.

``id`` is derived from the source document and the section heading rather than
generated, so re-seeding an edited document updates the passage in place. A
random primary key would make every re-seed append a second copy of the same
paragraph, and search would then return the same text twice while pushing a
genuinely different passage out of ``top_k``.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlmodel import Field

from app.core.configs.config import settings
from app.models.base import BaseModel


class KnowledgeChunk(BaseModel, table=True):
    """One retrievable passage from the training and nutrition knowledge base."""

    __tablename__ = "knowledge_chunks"

    # "{document-slug}#{section-slug}" — stable across re-seeds of an unchanged
    # document, and readable in a log line, which a hash of the body is not.
    id: str = Field(primary_key=True)

    # Human-readable document title. This is what `search_knowledge` reports as
    # `source`, so it ends up in front of the user as the citation.
    source: str = Field(index=True)
    heading: str
    # Position within the source document, so a caller can restore reading order.
    chunk_index: int

    # The embedded text, heading included. Storing exactly what was embedded is
    # what makes a re-embed verifiable: `content_hash` over this column decides
    # whether the seeder pays for the passage again.
    text: str = Field(sa_column=Column(Text, nullable=False))
    content_hash: str

    embedding: list[float] = Field(
        sa_column=Column(Vector(settings.KNOWLEDGE_EMBEDDING_DIM), nullable=False)
    )
