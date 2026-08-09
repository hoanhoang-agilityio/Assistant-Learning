"""Plan version history.

Full snapshots live here rather than in graph state:
LangGraph re-serialises the whole state after *every* node, so eight versions of
a full plan JSON in state would be rewritten many times per turn, and the cost
grows quadratically. State keeps only a light ``VersionRef`` index and reads a
snapshot from this table when one is actually needed.

**Versioning is append-only.** Restoring v1 creates v4 whose content is v1's,
with ``restored_from`` pointing at v1 and ``parent_id`` at v3. v2 and v3 remain
— otherwise the user cannot undo their undo, and they will want to.

``profile_hash`` and ``rubric_version`` are what make an old verify report
meaningful. If the profile is unchanged and the rubric is the same, re-running
the verifiers is guaranteed to give the same answer and can be skipped. If
either moved, the stored verdict no longer describes the current user and the
plan must be re-checked.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlmodel import Field

from app.models.base import BaseModel


class PlanVersion(BaseModel, table=True):
    """One immutable snapshot of an approved plan."""

    __tablename__ = "plan_versions"

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    # The conversation this snapshot came out of. This is the edge the episodic
    # layer walks: a session summary says what the user and the assistant did,
    # and this says which plan came of it. Without it the two can only be
    # correlated by timestamp, which silently misattributes a version whenever
    # a user has two sessions open.
    #
    # Nullable because an anonymous turn never reaches `_snapshot`'s write path,
    # because every row written before this column existed has no session to
    # point at — and because deleting a conversation nulls it. This table
    # outranks `session`: a user deleting a chat must keep the plan they train
    # on, so the constraint is ON DELETE SET NULL (see the migration), never
    # CASCADE and never the default RESTRICT.
    session_id: str | None = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("session.id", ondelete="SET NULL"), nullable=True, index=True
        ),
    )

    label: str = Field(default="")
    plan: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    macros: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    profile_hash: str = Field(default="", index=True)
    rubric_version: str = Field(default="")

    # Both unused until the revert branch exists. Declared now so the table is
    # not migrated a second time to add them.
    parent_id: str | None = Field(default=None)
    restored_from: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
