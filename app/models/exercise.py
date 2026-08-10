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

from sqlalchemy import JSON, Column, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, String

from app.models.base import BaseModel

# The two ways a set of a movement is counted. Exported because the seed
# validator, the catalog and the renderer all match on them, and a fourth
# spelling of the string "seconds" is exactly how a renderer silently stops
# recognising a unit.
UNIT_REPS = "reps"
UNIT_SECONDS = "seconds"
UNITS = (UNIT_REPS, UNIT_SECONDS)


def _text_array() -> Column:
    """Build a non-null Postgres ``text[]`` column defaulting to empty.

    Returns:
        The configured column.
    """
    return Column(ARRAY(String()), nullable=False, server_default="{}")


def _unit_column() -> Column:
    """Build the non-null ``unit`` column.

    The server default is what lets the migration add this to a populated table
    without touching the 103 existing rows.

    Returns:
        The configured column.
    """
    return Column(String(), nullable=False, server_default=UNIT_REPS)


class Exercise(BaseModel, table=True):
    """One movement in the catalog.

    Deliberately carries no sets or reps. Those belong to a template slot — an
    exercise is a movement, and the same movement takes different set and rep
    prescriptions in different programmes.

    ``unit`` and ``duration_seconds`` are the exception, and only because the
    slot cannot know them: a template slot prescribes a rep range for a
    *pattern*, and ``anti_extension`` is filled by both the ab wheel, which is
    counted in reps, and the plank, which is held for time. The unit is a
    property of the movement, so it lives here — see ``_render_plan``.
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

    # How a prescription of this movement is counted. `reps` for all but a
    # handful of isometric holds, which is why it defaults rather than being
    # stated 103 times in the seed.
    unit: str = Field(default=UNIT_REPS, sa_column=_unit_column())

    # ``[low, high]`` seconds per set, and only meaningful when ``unit`` is
    # ``seconds``. Held separately from the slot's rep range rather than
    # reinterpreting it: the template author wrote `[12, 20]` meaning
    # repetitions, and reading those same numbers as seconds would prescribe a
    # 12-second plank — a different wrong answer, not a fix.
    duration_seconds: list[int] | None = Field(
        default=None, sa_column=Column(ARRAY(Integer()), nullable=True)
    )
