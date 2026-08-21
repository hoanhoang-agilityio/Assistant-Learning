"""Chat session model.

Also the home of episodic memory. A session is what the user experienced as one
conversation, and ``summary`` is what survives of it once the checkpointer's
thread stops being read — the checkpointer is keyed by ``thread_id = id``, so
without this column nothing a user did in one session is visible from the next.

The summary lives on this row rather than in a ``session_summaries`` table: the
relationship is 1-1, every reader wants it alongside the session it describes,
and a separate table would buy a join and no capability.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Session(BaseModel, table=True):
    """A conversation session owned by a user."""

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(default="")
    username: str | None = Field(default=None)
    user: "User" = Relationship(back_populates="sessions")

    # What happened in this conversation, in the assistant's words. Empty until
    # the session goes idle and the background summariser fills it — and empty
    # forever if that call failed, which is deliberate: see `summarized_at`.
    summary: str = Field(default="")

    # The claim column, not a completion marker. It is set *before* the LLM call
    # by whichever worker won the atomic UPDATE, so a summary is attempted
    # exactly once. A failed attempt therefore leaves `summary` empty and is
    # never retried — a session that always fails must not burn an LLM call on
    # every subsequent turn, and a missing summary costs recall, not a turn.
    summarized_at: datetime | None = Field(default=None, index=True)

    # Last time a turn ran in this session. The only signal available for "this
    # conversation is over", since nothing marks a session as ended.
    last_activity_at: datetime | None = Field(default=None, index=True)
