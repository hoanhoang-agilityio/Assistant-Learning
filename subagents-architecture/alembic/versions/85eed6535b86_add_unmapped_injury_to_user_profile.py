"""add unmapped injury to user profile

Records an injury the user described in words the contraindication rubric has no
rule for.

Without it, ``injuries`` is a required field whose only valid values are the
rubric's two keys. A user who says "I have a bad lower back" answers the
question, the extractor correctly declines to map it onto a rule that does not
fit, the gate sees nothing, and asks again — forever. Storing the description
ends the loop and lets every plan state plainly that nothing screens for it

``server_default=""`` is not decoration. The column is NOT NULL, and the first
attempt at this migration omitted the default: Postgres rejected the ALTER
because the existing profile rows had no value, and the whole migration rolled
back. Any NOT NULL column added to a populated table needs one.

Revision ID: 85eed6535b86
Revises: aae63dea752d
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (AutoString and friends appear in generated DDL)

from alembic import op

revision: str = "85eed6535b86"
down_revision: str | None = "aae63dea752d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_profile",
        sa.Column(
            "unmapped_injury",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_profile", "unmapped_injury")
