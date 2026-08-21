"""Template library access.

**This is where the sets and reps in a generated plan come from.** Every set
count, rep range and RIR target is copied from a slot in one of these
templates. No model produces those numbers, and ``assemble_plan`` validates that
the assembled plan still matches the template it names.

A template is a skeleton of *slots*. A slot names a movement pattern and its
prescription; which exercise fills it is the one decision left to the LLM, and
it chooses from a list ``app/services/catalog.py`` has already filtered.

Held in process for the same reason the catalog is: a handful of rows, read on
every build, changed by a seed rather than at runtime. ``query_templates``
therefore filters the cached copy rather than issuing SQL — the result is
identical and does not depend on the database being reachable mid-build.
"""

from typing import Any

from sqlmodel import Session, select

from app.core.logging import logger
from app.models.database import engine
from app.models.template import Template

_CACHE: dict[str, dict[str, Any]] | None = None


def _to_dict(template: Template) -> dict[str, Any]:
    """Convert a row to the shape every caller reads.

    ``template_id`` rather than ``id``, because that is the key a stored plan
    records and what ``get_template`` is looked up by downstream.

    Args:
        template: The ORM row.

    Returns:
        The template as a plain dict.
    """
    return {
        "template_id": template.id,
        "name": template.name,
        "days_per_week": template.days_per_week,
        "goal": list(template.goal),
        "level": list(template.level),
        "popularity": template.popularity,
        "days": list(template.days),
    }


def load_templates(refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return the whole library, keyed by ``template_id``.

    Args:
        refresh: Re-read from Postgres instead of using the cached copy.

    Returns:
        Every template. Empty when the table has not been seeded.

    Raises:
        RuntimeError: Two templates share a ``slot_id``. That id is the key the
            LLM returns its exercise choice against, so a collision applies one
            choice to two slots — the plan assembles and is quietly not the
            programme the template describes.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    with Session(engine) as session:
        rows = session.exec(select(Template)).all()

    library = {row.id: _to_dict(row) for row in rows}

    seen: dict[str, str] = {}
    for template_id, template in library.items():
        for day in template["days"]:
            for slot in day["slots"]:
                owner = seen.setdefault(slot["slot_id"], template_id)
                if owner != template_id:
                    raise RuntimeError(
                        f"duplicate slot_id '{slot['slot_id']}' in '{template_id}' and '{owner}'"
                    )

    _CACHE = library
    logger.info("templates_loaded", template_count=len(_CACHE), slot_count=len(seen))
    return _CACHE


def query_templates(
    days_per_week: int, goal: str, level: int, limit: int = 3
) -> list[dict[str, Any]]:
    """Return templates matching hard criteria, most popular first.

    Deterministic and total: the same inputs always give the same list, and the
    filters are exact matches rather than preferences. An empty result is
    meaningful — it means the user's constraints have no template, which
    ``select_template`` must report immediately rather than letting the request
    fail later at verify.

    Args:
        days_per_week: Sessions the user can train.
        goal: Training goal, e.g. ``"fat_loss"``.
        level: Experience level; a template applies if it lists this level.
        limit: Maximum templates to return.

    Returns:
        Matching templates, ordered by descending popularity. Empty when nothing
        matches.
    """
    matches = [
        template
        for template in load_templates().values()
        if template["days_per_week"] == days_per_week
        and goal in template["goal"]
        and level in template["level"]
    ]
    matches.sort(key=lambda template: template["popularity"], reverse=True)
    return matches[:limit]


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return one template by id.

    Args:
        template_id: The template's id, e.g. ``"upper_lower_4day"``.

    Returns:
        The template, or ``None`` when no such template exists.
    """
    return load_templates().get(template_id)


def iter_slots(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a template's slots, tagging each with its day.

    Args:
        template: A template from this library.

    Returns:
        Every slot, each with a ``day_name`` key added.
    """
    return [{**slot, "day_name": day["name"]} for day in template["days"] for slot in day["slots"]]


__all__ = ["get_template", "iter_slots", "load_templates", "query_templates"]
