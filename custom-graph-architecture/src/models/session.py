"""Conversation session model.

The session id is also the graph's ``thread_id``, so this row is what ties a durable
LangGraph checkpoint to the user allowed to resume it. The checkpoint tables themselves
are owned by ``AsyncPostgresSaver`` and carry no ownership information — see
``src/models/table_ownership.py``.
"""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from src.models.base import BaseModel

if TYPE_CHECKING:
    from src.models.user import User


class Session(BaseModel, table=True):
    """A conversation session owned by a user."""

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(default="")
    username: str | None = Field(default=None)
    user: "User" = Relationship(back_populates="sessions")
