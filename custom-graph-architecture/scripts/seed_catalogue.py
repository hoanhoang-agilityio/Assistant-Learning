"""Load the training catalogue into Postgres.

Idempotent: rows are upserted by primary key, so re-running after editing ``data/`` brings
the database to match the files rather than duplicating or failing.

    uv run python scripts/seed_catalogue.py
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from src.models.catalogue import Exercise, WorkoutTemplate
from src.schemas import Exercise as ExerciseSchema
from src.schemas import WorkoutTemplate as TemplateSchema
from src.services.database import close_engine, session_factory
from src.utils.logging import logger

DATA_DIR = Path("data")


def _exercise_rows() -> list[dict[str, Any]]:
    """Read and validate the exercise catalogue."""
    rows = json.loads((DATA_DIR / "exercises.json").read_text())
    return [ExerciseSchema.model_validate(row).model_dump(mode="json") for row in rows]


def _template_rows() -> list[dict[str, Any]]:
    """Read and validate the templates, flattening each into its table's shape."""
    rows = json.loads((DATA_DIR / "templates.json").read_text())
    templates = [TemplateSchema.model_validate(row) for row in rows]
    return [
        template.model_dump(mode="json") | {"days_per_week": template.days_per_week}
        for template in templates
    ]


async def _upsert(model: type, rows: list[dict[str, Any]]) -> None:
    """Insert the rows, replacing any that are already there."""
    if not rows:
        return

    statement = insert(model)
    statement = statement.on_conflict_do_update(
        index_elements=["id"],
        set_={key: statement.excluded[key] for key in rows[0] if key != "id"},
    )
    async with session_factory() as session:
        await session.execute(statement, rows)
        await session.commit()


async def main() -> None:
    """Seed both catalogue tables from ``data/``."""
    exercises, templates = _exercise_rows(), _template_rows()

    await _upsert(Exercise, exercises)
    await _upsert(WorkoutTemplate, templates)
    await close_engine()

    logger.info("catalogue_seeded", exercises=len(exercises), templates=len(templates))


if __name__ == "__main__":
    asyncio.run(main())
