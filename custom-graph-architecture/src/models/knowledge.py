"""The knowledge base table: the embedded passages the QA agent retrieves from."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from src.core.configs.config import settings


class KnowledgeChunk(SQLModel, table=True):
    """One retrievable passage from the nutrition and injury knowledge base."""

    __tablename__ = "knowledge_chunks"

    id: str = Field(primary_key=True)
    source: str = Field(index=True)
    heading: str
    chunk_index: int
    text: str = Field(sa_column=Column(Text, nullable=False))
    content_hash: str
    embedding: list[float] = Field(
        sa_column=Column(
            Vector(settings.KNOWLEDGE_EMBEDDING_DIM), nullable=False)
    )
