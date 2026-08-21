"""add session summaries and the plan-version session link

Gives the application an episodic memory that survives a session boundary. The
LangGraph checkpointer is keyed by ``thread_id = session.id``, so everything a
user did in one conversation was invisible from the next; ``session.summary``
is what carries across.

``session.summarized_at`` is a claim column rather than a completion marker. The
background summariser sets it *before* calling the model, in an
``UPDATE ... WHERE summarized_at IS NULL`` whose row count decides the winner,
so several uvicorn workers cannot each summarise the same session. That also
means a failed summary is never retried, which is the intended trade: a session
whose summary always fails must not cost an LLM call on every later turn.

``plan_versions.session_id`` is the edge between the two halves of episodic
memory — what the conversation was about, and which plan came out of it. It is
nullable because rows written before this revision have no session to point at,
and because an anonymous turn never writes a version at all.

Revision ID: d7e3f1a92b48
Revises: c4a91f7b2d30
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (AutoString and friends appear in generated DDL)

from alembic import op

revision: str = "d7e3f1a92b48"
down_revision: str | None = "c4a91f7b2d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing sessions get an empty summary and a NULL claim, so the sweep
    # treats them as never attempted and picks them up once they go idle.
    op.add_column(
        "session",
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )
    op.add_column("session", sa.Column("summarized_at", sa.DateTime(), nullable=True))
    op.add_column("session", sa.Column("last_activity_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_session_summarized_at"), "session", ["summarized_at"], unique=False)
    op.create_index(
        op.f("ix_session_last_activity_at"), "session", ["last_activity_at"], unique=False
    )

    op.add_column(
        "plan_versions",
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        op.f("ix_plan_versions_session_id"), "plan_versions", ["session_id"], unique=False
    )
    # ON DELETE SET NULL, not the default RESTRICT and certainly not CASCADE.
    # `plan_versions` is append-only and outranks the conversation it came from:
    # deleting a chat must not destroy the plan the user is training on, and must
    # not start failing because a plan points at it. The version survives; only
    # the link to a conversation that no longer exists goes away.
    op.create_foreign_key(
        "fk_plan_versions_session_id_session",
        "plan_versions",
        "session",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_plan_versions_session_id_session", "plan_versions", type_="foreignkey")
    op.drop_index(op.f("ix_plan_versions_session_id"), table_name="plan_versions")
    op.drop_column("plan_versions", "session_id")

    op.drop_index(op.f("ix_session_last_activity_at"), table_name="session")
    op.drop_index(op.f("ix_session_summarized_at"), table_name="session")
    op.drop_column("session", "last_activity_at")
    op.drop_column("session", "summarized_at")
    op.drop_column("session", "summary")
