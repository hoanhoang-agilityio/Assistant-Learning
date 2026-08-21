"""Load the normalized exercise catalog into Postgres.

Idempotent: existing rows are updated in place and new ones inserted, so running
it twice is a no-op rather than a primary-key violation. Nothing is deleted —
removing an exercise that a stored plan references would leave that plan
unreadable, so retirement is a separate, deliberate operation.

Run::

    uv run python scripts/check_exercise_seed.py   # validate the catalog file
    uv run alembic upgrade head                    # create the table
    uv run python scripts/seed_catalog.py          # load it

The seed file is the source of truth and has been reviewed by hand. Re-seeding
is how a change to it reaches the running application: `filter_candidates`
gates on `skill_level` and sorts by `fatigue_cost`, so an unseeded edit means
the app keeps choosing exercises by the old numbers.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.core.logging import logger  # noqa: E402
from app.models.database import engine  # noqa: E402
from app.models.exercise import UNIT_REPS, Exercise  # noqa: E402

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_seed.json"

_FIELDS = (
    "name",
    "movement_pattern",
    "primary_muscles",
    "secondary_muscles",
    "equipment",
    "joint_actions",
    "loaded_positions",
    "contribution",
    "skill_level",
    "fatigue_cost",
)

# Stated only on the rows that differ from the column default — `unit` appears
# on the handful of movements held for time, and nowhere else. Kept apart from
# `_FIELDS` because the update path indexes those directly, which would raise
# for every row that sensibly omits them.
#
# Written on update even when absent, rather than skipped: the seed file is the
# source of truth, so deleting `unit` from an entry must return that row to
# reps rather than leave the old value in place.
_OPTIONAL_FIELDS: dict[str, object] = {
    "unit": UNIT_REPS,
    "duration_seconds": None,
}


def seed(rows: list[dict]) -> tuple[int, int]:
    """Upsert catalog rows into the ``exercises`` table.

    Args:
        rows: Normalized catalog entries.

    Returns:
        ``(inserted, updated)`` counts.
    """
    inserted = 0
    updated = 0

    with Session(engine) as session:
        existing = {row.id: row for row in session.exec(select(Exercise)).all()}

        for entry in rows:
            current = existing.get(entry["id"])
            if current is None:
                session.add(Exercise(**entry))
                inserted += 1
                continue

            for field in _FIELDS:
                setattr(current, field, entry[field])
            for field, default in _OPTIONAL_FIELDS.items():
                setattr(current, field, entry.get(field, default))
            session.add(current)
            updated += 1

        session.commit()

    return inserted, updated


def main() -> int:
    """Seed the catalog and report what changed.

    Returns:
        Process exit code: 0 on success, 1 when the catalog file is missing.
    """
    if not _CATALOG_FILE.exists():
        print(
            f"missing {_CATALOG_FILE}. "
            "The catalog file is the source of truth for the exercises table.",
            file=sys.stderr,
        )
        return 1

    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    inserted, updated = seed(rows)

    logger.info("catalog_seeded", inserted=inserted, updated=updated, total=len(rows))
    print(f"seeded {len(rows)} exercises: {inserted} inserted, {updated} updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
