"""Chat session model."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Session(BaseModel, table=True):
    """A conversation session owned by a user.

    The unit a session token is scoped to. ``username`` is copied from the owner
    at creation time so downstream personalisation does not need to join back to
    the user row on every turn.
    """

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(default="")
    username: str | None = Field(default=None)
    user: "User" = Relationship(back_populates="sessions")
