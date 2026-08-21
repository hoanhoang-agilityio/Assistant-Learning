"""Load the template library and the rubrics into Postgres.

The counterpart to ``scripts/seed_catalog.py``: ``data/template_seed.json`` and
``data/rubric_seed.json`` are the source of truth, this moves them into the
tables the application reads.

Run::

    uv run python scripts/check_config_seed.py   # validate both files
    uv run alembic upgrade head                  # create the tables
    uv run python scripts/seed_config.py         # load them

Templates upsert in place, like exercises: a stored plan references a template
by id, and giving the same programme a new id would orphan it.

Rubrics do not. Seeding an existing ``(name, version)`` whose payload has
changed **fails** rather than updating, because that row may already be cited by
a stored verify report — rewriting it makes that verdict unreproducible while
leaving it looking intact. Change a rule and bump ``rubric_version``; the new
version is inserted beside the old one and ``is_active`` moves to it.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.core.logging import logger  # noqa: E402
from app.models.database import engine  # noqa: E402
from app.models.rubric import Rubric  # noqa: E402
from app.models.template import Template  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_RUBRIC_SEED = _ROOT / "data" / "rubric_seed.json"
_TEMPLATE_SEED = _ROOT / "data" / "template_seed.json"

_TEMPLATE_FIELDS = ("name", "days_per_week", "goal", "level", "popularity", "days")


class SeedConflict(RuntimeError):
    """A rubric version already in the table was seeded with a different body."""


def seed_templates(entries: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert the template library.

    Args:
        entries: Parsed ``template_seed.json``.

    Returns:
        ``(inserted, updated)`` counts.
    """
    inserted = 0
    updated = 0

    with Session(engine) as session:
        existing = {row.id: row for row in session.exec(select(Template)).all()}

        for entry in entries:
            row = existing.get(entry["template_id"])
            if row is None:
                session.add(
                    Template(
                        id=entry["template_id"],
                        **{field: entry[field] for field in _TEMPLATE_FIELDS},
                    )
                )
                inserted += 1
                continue

            for field in _TEMPLATE_FIELDS:
                setattr(row, field, entry[field])
            session.add(row)
            updated += 1

        session.commit()

    return inserted, updated


def seed_rubrics(documents: dict[str, Any]) -> tuple[int, int]:
    """Insert each rubric at its version and make that version active.

    Args:
        documents: Parsed ``rubric_seed.json``, keyed by rubric name.

    Returns:
        ``(inserted, activated)`` — rows written, and rows that became the
        version the application reads.

    Raises:
        SeedConflict: A ``(name, version)`` already present has a different
            payload. Bump ``rubric_version`` instead of rewriting history.
    """
    inserted = 0
    activated = 0

    with Session(engine) as session:
        rows = session.exec(select(Rubric)).all()
        existing = {(row.name, row.version): row for row in rows}

        for name, payload in documents.items():
            version = payload["rubric_version"]
            current = existing.get((name, version))

            if current is None:
                session.add(Rubric(name=name, version=version, payload=payload, is_active=False))
                inserted += 1
            elif current.payload != payload:
                raise SeedConflict(
                    f"{name} {version} is already stored with a different body. A verify report "
                    "may cite this version; bump rubric_version rather than rewriting it."
                )

        # Flipped only after every document is staged, so a failure above leaves
        # the previous version serving rather than half of the new one.
        for row in rows:
            if row.is_active and row.version != documents.get(row.name, {}).get("rubric_version"):
                row.is_active = False
                session.add(row)

        session.commit()

        for name, payload in documents.items():
            row = session.exec(
                select(Rubric).where(
                    Rubric.name == name, Rubric.version == payload["rubric_version"]
                )
            ).one()
            if not row.is_active:
                row.is_active = True
                session.add(row)
                activated += 1

        session.commit()

    return inserted, activated


def main() -> int:
    """Seed both tables and report what changed.

    Returns:
        Process exit code: 0 on success, 1 when a seed file is missing or a
        rubric version conflicts with what is stored.
    """
    for path in (_RUBRIC_SEED, _TEMPLATE_SEED):
        if not path.exists():
            print(f"missing {path}. It is the source of truth for its table.", file=sys.stderr)
            return 1

    templates = json.loads(_TEMPLATE_SEED.read_text(encoding="utf-8"))
    rubrics = json.loads(_RUBRIC_SEED.read_text(encoding="utf-8"))

    template_inserted, template_updated = seed_templates(templates)
    try:
        rubric_inserted, rubric_activated = seed_rubrics(rubrics)
    except SeedConflict as conflict:
        print(f"ERROR {conflict}", file=sys.stderr)
        return 1

    logger.info(
        "config_seeded",
        templates=len(templates),
        template_inserted=template_inserted,
        template_updated=template_updated,
        rubrics=len(rubrics),
        rubric_inserted=rubric_inserted,
        rubric_activated=rubric_activated,
    )
    print(
        f"seeded {len(templates)} templates: {template_inserted} inserted, "
        f"{template_updated} updated"
    )
    print(
        f"seeded {len(rubrics)} rubrics: {rubric_inserted} inserted, {rubric_activated} activated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
