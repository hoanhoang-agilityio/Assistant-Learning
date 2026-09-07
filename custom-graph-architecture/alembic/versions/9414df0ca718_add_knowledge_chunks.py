"""knowledge base: embedded passages for retrieval

The `vector` column depends on the extension created by the first revision, and the HNSW
index is built for `vector_cosine_ops` because retrieval orders by the cosine distance
operator `<=>`. An index built for a different operator class would simply be ignored,
leaving every question to sequentially scan the table.

Revision ID: 9414df0ca718
Revises: 884ae98d4d53
Create Date: 2026-08-25 16:02:57.461388
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "9414df0ca718"
down_revision: str | None = "884ae98d4d53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("heading", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source"),
        "knowledge_chunks",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_embedding",
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Revert the schema change."""
    op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_source"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
