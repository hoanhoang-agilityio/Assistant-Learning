"""Programme templates — where every set and rep in a plan comes from.

No model produces those numbers. ``assemble_plan`` copies them out of a slot and
then validates that the assembled plan still matches the template it claims, so
this table is load-bearing in the same way the exercise catalog is: the LLM
picks *which exercise* fills a slot, and nothing else.

``days`` holds the day → slot structure whole. Slots are never queried
independently — ``iter_slots`` flattens the entire template on every read — so a
``template_slots`` table would buy a join and no capability.

``goal`` and ``level`` are arrays because a template applies to several of each,
and ``query_templates`` asks for membership. That is a containment query, which
is what the GIN indexes in the migration serve.
"""

from sqlalchemy import JSON, Column, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, String

from app.models.base import BaseModel


class Template(BaseModel, table=True):
    """One programme skeleton."""

    __tablename__ = "templates"

    # The file stem the templates were previously keyed by, e.g.
    # "upper_lower_4day". Stored plans reference it, so it must stay stable.
    id: str = Field(primary_key=True)
    name: str

    days_per_week: int = Field(index=True)
    goal: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String()), nullable=False, server_default="{}"),
    )
    level: list[int] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Integer()), nullable=False, server_default="{}"),
    )

    # Breaks ties between templates that match the same request. Descending, so
    # the same inputs always select the same template.
    popularity: int = Field(default=0)

    days: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
