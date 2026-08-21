"""drop the mem0 tables

mem0 is gone as a backend. Measured against the running database it held 132
rows for one user and not a single standing qualitative fact: model output
echoed back (verdicts, macro dumps, exercise listings), generic training advice
that belongs to the curated knowledge base, and duplicates that its own dedupe
could not collapse because every turn phrased the same fact differently. Every
category it carried already has an owner — ``user_profile``, ``plan_versions``,
``session.summary``, ``knowledge_chunks`` — and semantic memory is now
``user_profile`` read by primary key, with no embedding and no top-k.

Two tables, neither with a SQLModel counterpart: ``longterm_memory`` is mem0's
pgvector store and ``mem0migrations`` its own bookkeeping. Both were listed in
``EXCLUDE_TABLES`` in ``alembic/env.py`` so autogenerate would not propose
dropping tables it did not create; that entry goes away with this revision, and
after it autogenerate sees a database with no mem0 in it at all.

``IF EXISTS`` on both, deliberately. mem0 created its tables lazily on first
initialisation, so any environment where it never ran — CI, a fresh clone, a
developer who never set an OpenAI key — has neither table, and this revision has
to be a no-op there rather than a failure.

The ``vector`` extension is left alone. ``knowledge_chunks`` uses it.

Revision ID: b1c47e0a9f52
Revises: d7e3f1a92b48
Create Date: 2026-08-09

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b1c47e0a9f52"
down_revision: str | None = "d7e3f1a92b48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TABLE IF EXISTS longterm_memory")
    op.execute("DROP TABLE IF EXISTS mem0migrations")


def downgrade() -> None:
    """Downgrade schema.

    Intentionally empty. These tables were created by mem0 itself, at runtime,
    to a schema this project never declared — and the dependency that knows that
    schema is removed in the same change. Recreating them here would mean
    guessing at someone else's DDL to produce empty tables nothing reads.

    The rows are not recoverable by a downgrade either way. That is the point of
    this revision being the last step of the phase rather than the first: every
    earlier step leaves the read and write paths dead but the data intact.
    """
