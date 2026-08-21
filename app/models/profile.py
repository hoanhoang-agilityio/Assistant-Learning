"""User training profile.

One row per user, not per session: body weight and injuries are facts about a
person, and re-asking for them every conversation would be the most obvious
failure this system could have.

Every field is nullable. The profile is built up across turns by
``extract_profile``, and which fields must be present before a given intent may
proceed is decided by ``REQUIRED_FIELDS`` in ``app/services/profile.py`` — a
deterministic constant, never a model's judgment about whether it has enough
"""

from datetime import UTC, datetime

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field

from app.models.base import BaseModel


def _text_array() -> Column:
    """Build a non-null Postgres ``text[]`` column defaulting to empty.

    Returns:
        The configured column.
    """
    return Column(ARRAY(String()), nullable=False, server_default="{}")


class UserProfile(BaseModel, table=True):
    """Training profile for one user."""

    __tablename__ = "user_profile"

    id: int | None = Field(default=None, primary_key=True)
    # Unique, not just indexed: two profile rows for one user would let two
    # concurrent turns each build a plan against a different body weight.
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)

    weight_kg: float | None = Field(default=None)
    height_cm: float | None = Field(default=None)
    age: int | None = Field(default=None)
    sex: str | None = Field(default=None)
    activity_level: str | None = Field(default=None)

    days_per_week: int | None = Field(default=None)
    level: int | None = Field(default=None)
    goal: str | None = Field(default=None)

    equipment: list[str] = Field(default_factory=list, sa_column=_text_array())
    injuries: list[str] = Field(default_factory=list, sa_column=_text_array())

    # Free text the user stated about what they like or want to avoid. Passed to
    # the planning agent as an extracted string rather than as a transcript, so
    # the planner cannot be steered by anything not deliberately extracted.
    preferences: str = Field(default="")

    # An injury the user described that the contraindication rubric has no rule
    # for. Stored so the gate stops re-asking and so every plan can say plainly
    # that nothing screens for it.
    unmapped_injury: str = Field(default="")

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
