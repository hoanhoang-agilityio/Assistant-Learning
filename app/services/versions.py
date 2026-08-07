"""Plan version storage.

Append-only. Nothing here updates or deletes a version: restoring an old plan
creates a *new* version whose content is the old one's.
Rewriting history would mean the user cannot undo an undo, and they will
want to.

The split between this module and graph state is the rule: full snapshots
live in Postgres, state carries only the light ``VersionRef`` index. LangGraph
re-serialises the whole state after every node, so keeping eight full plan JSONs
there makes every turn quadratically more expensive to checkpoint.
"""

import uuid
from typing import Any

from sqlmodel import Session, col, select

from app.models.database import engine
from app.models.plan_version import PlanVersion
from app.schemas.graph import VersionRef

# How many versions the in-state index carries. Older ones stay in Postgres and
# are reachable by id; the index exists so `resolve_version` can map "the
# original plan" onto a version without loading every snapshot.
_INDEX_LIMIT = 20


async def insert_version(
    user_id: int,
    plan: dict[str, Any],
    macros: dict[str, Any],
    profile_hash: str,
    rubric_version: str,
    label: str = "",
    parent_id: str | None = None,
    restored_from: str | None = None,
) -> VersionRef:
    """Store a plan snapshot and return its index entry.

    Args:
        user_id: Owner of the plan.
        plan: The full plan JSON.
        macros: Macros belonging to that plan.
        profile_hash: Fingerprint of the profile it was built for.
        rubric_version: Rubric version its verify report was produced under.
        label: Human-readable name, defaulted to a version number.
        parent_id: The version this one supersedes.
        restored_from: Set when this version's content came from an older one.

    Returns:
        The ``VersionRef`` to put in state.
    """
    version_id = str(uuid.uuid4())

    with Session(engine) as session:
        existing = session.exec(select(PlanVersion).where(PlanVersion.user_id == user_id)).all()
        row = PlanVersion(
            id=version_id,
            user_id=user_id,
            label=label or f"v{len(existing) + 1}",
            plan=plan,
            macros=macros,
            profile_hash=profile_hash,
            rubric_version=rubric_version,
            parent_id=parent_id,
            restored_from=restored_from,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        ref = VersionRef(version_id=row.id, label=row.label, created_at=row.created_at.isoformat())
    return ref


async def get_version(version_id: str) -> PlanVersion | None:
    """Load one full snapshot.

    Args:
        version_id: The version to load.

    Returns:
        The stored version, or ``None`` when no such version exists.
    """
    with Session(engine) as session:
        return session.get(PlanVersion, version_id)


async def version_index(user_id: int) -> list[VersionRef]:
    """List a user's versions, newest first, as light index entries.

    Deliberately returns refs rather than rows: the caller puts this in graph
    state, and a full snapshot there would be re-serialised on every node.

    Args:
        user_id: Owner of the plans.

    Returns:
        Up to ``_INDEX_LIMIT`` version refs, newest first.
    """
    with Session(engine) as session:
        rows = session.exec(
            select(PlanVersion)
            .where(PlanVersion.user_id == user_id)
            .order_by(col(PlanVersion.created_at).desc())
            .limit(_INDEX_LIMIT)
        ).all()

    return [
        VersionRef(version_id=row.id, label=row.label, created_at=row.created_at.isoformat())
        for row in rows
    ]


__all__ = ["get_version", "insert_version", "version_index"]
