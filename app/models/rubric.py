"""Versioned rubrics — the rules that decide what passes.

These were read from JSON files in the package at import. Postgres serves them
now, which removes the property that made files safe: a rubric change used to be
a reviewable commit, and in a table it can be one ``UPDATE``.

Two things put that guarantee back, and neither is optional:

* ``data/rubric_seed.json`` remains the source of truth. Rows are written by
  ``scripts/seed_config.py`` from that file, so a rule still changes through a
  reviewed diff — the table is a serving copy, not the authority.
* The primary key is ``(name, version)``, so seeding a new version *inserts*.
  A row that produced a verdict is never rewritten, which is what lets
  ``plan_versions.rubric_version`` reproduce an old verify report.

``is_active`` names the version the running application reads. Exactly one row
per name carries it; the seeder flips it as the last step so a partially seeded
version is never served.
"""

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.models.base import BaseModel


class Rubric(BaseModel, table=True):
    """One rubric document at one version."""

    __tablename__ = "rubrics"

    # "macro_rules", "volume_landmarks" or "contraindications".
    name: str = Field(primary_key=True)
    # Mirrors the ``rubric_version`` inside ``payload``, lifted out so a version
    # can be selected without parsing the document.
    version: str = Field(primary_key=True)

    # The rubric exactly as the checks consume it. Stored whole rather than
    # normalized into columns: the three documents have three different shapes,
    # every reader takes the whole thing, and a column layout would have to be
    # migrated each time a rule gains a field.
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    is_active: bool = Field(default=False, index=True)
