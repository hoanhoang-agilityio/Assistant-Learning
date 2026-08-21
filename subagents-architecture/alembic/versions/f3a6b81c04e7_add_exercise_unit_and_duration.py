"""add unit and duration_seconds to exercises

A template slot prescribes sets, reps and RIR for a movement *pattern*, and the
planner fills the slot with whichever catalog exercise matches. That works until
the pattern admits both a rep-counted and a time-held movement:
``anti_extension`` is filled by the ab wheel and the dead bug, which are counted
in repetitions, and by the plank, which is held for time. Every one of them was
rendered as "3 sets x 12-20 reps", so the plank came out prescribed in reps.

The unit belongs to the movement, not to the slot, which is why it lands here
rather than in ``templates``. Correcting the slot's rep range instead would fix
the plank by breaking the ab wheel.

``duration_seconds`` is a separate range rather than a reinterpretation of the
slot's ``reps``. The template author wrote ``[12, 20]`` meaning repetitions;
reading those same two numbers as seconds would prescribe a 12-second plank,
which is a different wrong answer rather than a fix.

``unit`` is NOT NULL with a server default, so this applies to the populated
catalog without a data migration: every existing row is a rep-counted movement,
which is what the default says. The seed then marks the handful of holds.
``duration_seconds`` is nullable because it is meaningless for them.

Revision ID: f3a6b81c04e7
Revises: b1c47e0a9f52
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (AutoString and friends appear in generated DDL)
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a6b81c04e7"
down_revision: str | None = "b1c47e0a9f52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "exercises",
        sa.Column("unit", sa.String(), nullable=False, server_default="reps"),
    )
    op.add_column(
        "exercises",
        sa.Column("duration_seconds", postgresql.ARRAY(sa.Integer()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("exercises", "duration_seconds")
    op.drop_column("exercises", "unit")
