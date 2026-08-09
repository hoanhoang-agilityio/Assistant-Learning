"""Exercise catalog.

Postgres rather than a vector store, every query
against this table is an exact set operation — does the user own this equipment,
does this exercise involve a forbidden joint action — and those are answered by
array containment with a GIN index, not by similarity. Embeddings are derived
data used only by ``resolve_exercise``; this table is the source of truth, and
an exercise name must never exist only in the vector store.

``joint_actions`` and ``loaded_positions`` are the columns the injury check reads.
They are what make a contraindication rule survive catalog growth: mapping an
injury to attributes catches an exercise added tomorrow, mapping it to names does
not.
"""

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, String

from app.models.base import BaseModel


def _text_array() -> Column:
    """Build a non-null Postgres ``text[]`` column defaulting to empty.

    Returns:
        The configured column.
    """
    return Column(ARRAY(String()), nullable=False, server_default="{}")


class Exercise(BaseModel, table=True):
    """One movement in the catalog.

    Deliberately carries no sets or reps. Those belong to a template slot — an
    exercise is a movement, and the same movement takes different set and rep
    prescriptions in different programmes.
    """

    __tablename__ = "exercises"

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    movement_pattern: str = Field(index=True)

    primary_muscles: list[str] = Field(default_factory=list, sa_column=_text_array())
    secondary_muscles: list[str] = Field(default_factory=list, sa_column=_text_array())
    equipment: list[str] = Field(default_factory=list, sa_column=_text_array())
    joint_actions: list[str] = Field(default_factory=list, sa_column=_text_array())
    loaded_positions: list[str] = Field(default_factory=list, sa_column=_text_array())

    # Fractional set credit per muscle, e.g. {"chest": 1.0, "triceps": 0.5}.
    # The volume check multiplies each set by these shares; counting a set as
    # whole for every muscle it touches inflates every weekly total.
    contribution: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    skill_level: int = Field(default=1)
    fatigue_cost: int = Field(default=1)
