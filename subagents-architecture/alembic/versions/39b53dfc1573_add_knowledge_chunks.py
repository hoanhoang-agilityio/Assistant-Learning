"""add knowledge chunks

Creates the ``knowledge_chunks`` table behind ``search_knowledge``
and the pgvector extension it needs.

``CREATE EXTENSION`` is issued here rather than assumed: the extension happens to
exist on the development database because mem0 created it for ``longterm_memory``,
which means a fresh deployment would only discover the omission when the first
migration failed on an unknown ``vector`` type. Nothing else in the schema
depends on a side effect of an optional feature being switched on.

The HNSW index is hand-written and must stay that way — Alembic's
``--autogenerate`` cannot express an index method or an operator class, so a
later revision will neither create it nor notice it is gone. ``alembic/env.py``
excludes the ``_hnsw`` suffix for the same reason it excludes ``_gin``: an index
Alembic did not write looks to it like one it should drop.

``vector_cosine_ops`` matches the ``<=>`` operator ``app/services/knowledge.py``
searches with. An index built for a different distance function is not a slower
index, it is an unused one.

Revision ID: 39b53dfc1573
Revises: 85eed6535b86
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (AutoString and friends appear in generated DDL)

from alembic import op
from app.core.configs.config import settings

revision: str = "39b53dfc1573"
down_revision: str | None = "85eed6535b86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_INDEX = "ix_knowledge_chunks_embedding_hnsw"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("heading", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(dim=settings.KNOWLEDGE_EMBEDDING_DIM),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source"), "knowledge_chunks", ["source"], unique=False
    )
    op.create_index(
        _EMBEDDING_INDEX,
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(_EMBEDDING_INDEX, table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_source"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    # The extension is left in place: mem0's `longterm_memory` also depends on
    # it, so dropping it here would break a table this revision never owned.
