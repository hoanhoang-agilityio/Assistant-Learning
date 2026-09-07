"""enable pgvector extension

The sole place the extension is created. It must stay the first revision so no later
migration can declare a ``vector`` column before the type exists, and it is what guarantees
the extension on a staging or production database nobody set up by hand.

Revision ID: 8376b79b1611
Revises:
Create Date: 2026-08-21 10:25:06.045866
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8376b79b1611"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the pgvector extension if it is not already present."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Deliberately a no-op.

    Dropping the extension would cascade into every table holding a ``vector`` column —
    the knowledge base among them. Removing pgvector is an operator decision, not
    something a schema downgrade should do silently.
    """
