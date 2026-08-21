"""Rubric access — the rules the verifiers judge a plan against.

Reads the active version of each rubric from Postgres and holds it in process.
Three small documents that change through a seed, not at runtime, so they are
loaded once; ``refresh=True`` exists for the tests and for admin tooling.

Loading is lazy on purpose. These used to be module-level constants parsed at
import, which meant importing any verifier opened a database connection as a
side effect — a script that only wanted to validate a JSON file would have
needed Postgres running. Every accessor here is a function call instead.

The version-agreement invariant that used to raise at import raises on first
load. ``scripts/check_config_seed.py`` catches it before seeding; this catches a
table that was edited around the seeder, which is the case where a verdict
would otherwise be stamped with a version that only partly describes it.
"""

from typing import Any

from sqlmodel import Session, select

from app.core.logging import logger
from app.models.database import engine
from app.models.rubric import Rubric

# The three the verifiers read. A missing one is an error at load rather than an
# AttributeError on the first plan that reaches that check.
_REQUIRED = ("macro_rules", "volume_landmarks", "contraindications")

_CACHE: dict[str, dict[str, Any]] | None = None


def load_rubrics(refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return the active rubrics, keyed by name.

    Args:
        refresh: Re-read from Postgres instead of using the cached copy.

    Returns:
        ``{"macro_rules": {...}, "volume_landmarks": {...},
        "contraindications": {...}}`` — each value the document exactly as the
        checks consume it.

    Raises:
        RuntimeError: A rubric has no active version, or the active versions
            disagree. Either makes a stored ``rubric_version`` unable to
            reproduce the verdict it labels.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    with Session(engine) as session:
        rows = session.exec(select(Rubric).where(Rubric.is_active)).all()

    active = {row.name: row for row in rows}

    missing = [name for name in _REQUIRED if name not in active]
    if missing:
        raise RuntimeError(
            f"no active rubric for {missing}. Run scripts/seed_config.py — the verifiers cannot "
            "judge a plan against rules that are not loaded."
        )

    versions = {row.version for row in active.values()}
    if len(versions) != 1:
        raise RuntimeError(f"active rubric versions disagree: {sorted(versions)}")

    _CACHE = {name: dict(row.payload) for name, row in active.items()}
    logger.info("rubrics_loaded", version=next(iter(versions)), names=sorted(_CACHE))
    return _CACHE


def macro_rules() -> dict[str, Any]:
    """Return the macro rubric.

    Returns:
        Protein, fat, deficit and floor rules.
    """
    return load_rubrics()["macro_rules"]


def volume_landmarks() -> dict[str, Any]:
    """Return the volume rubric.

    Returns:
        Weekly hard-set landmarks per muscle, plus frequency and session caps.
    """
    return load_rubrics()["volume_landmarks"]


def contraindications() -> dict[str, Any]:
    """Return the injury rubric.

    Returns:
        Per-injury joint actions and loaded positions to avoid.
    """
    return load_rubrics()["contraindications"]


def rubric_version() -> str:
    """Return the version every active rubric shares.

    This is what a stored verify report records, so an old verdict can be
    reproduced by reading the rubric rows at that version.

    Returns:
        The shared version, e.g. ``"2026.2"``.
    """
    return load_rubrics()["macro_rules"]["rubric_version"]


__all__ = [
    "contraindications",
    "load_rubrics",
    "macro_rules",
    "rubric_version",
    "volume_landmarks",
]
