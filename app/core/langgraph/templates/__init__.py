"""Template library, loaded from git.

**This is the answer to "where do sets and reps come from".** Every set count,
rep range and RIR target in a generated plan is copied from a slot in one of
these files. No model produces those numbers, and ``assemble_plan`` validates
that the assembled plan still matches the template.

Templates are configuration, not data: they change through a reviewed commit,
not an UPDATE. Files are read once at import.

A template is a skeleton of *slots*. A slot names a movement pattern and its
prescription; which exercise fills it is the one decision left to the LLM, and
it chooses from a list the catalog already filtered.
"""

import json
from pathlib import Path
from typing import Any

_TEMPLATES_DIR = Path(__file__).parent

TEMPLATES: dict[str, dict[str, Any]] = {
    path.stem: json.loads(path.read_text(encoding="utf-8"))
    for path in sorted(_TEMPLATES_DIR.glob("*.json"))
}

# A slot_id must be unique across the whole library: it is the key the LLM
# returns a choice against, and a collision would silently apply one choice to
# two slots. Checked at import so the process refuses to start rather than
# building a subtly wrong plan.
_SEEN: dict[str, str] = {}
for _template_id, _template in TEMPLATES.items():
    for _day in _template["days"]:
        for _slot in _day["slots"]:
            _slot_id = _slot["slot_id"]
            if _slot_id in _SEEN:
                raise RuntimeError(
                    f"duplicate slot_id '{_slot_id}' in '{_template_id}' and '{_SEEN[_slot_id]}'"
                )
            _SEEN[_slot_id] = _template_id


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
        for template in TEMPLATES.values()
        if template["days_per_week"] == days_per_week
        and goal in template["goal"]
        and level in template["level"]
    ]
    matches.sort(key=lambda template: template["popularity"], reverse=True)
    return matches[:limit]


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return one template by id.

    Args:
        template_id: The template's file stem, e.g. ``"upper_lower_4day"``.

    Returns:
        The template, or ``None`` when no such template exists.
    """
    return TEMPLATES.get(template_id)


def iter_slots(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a template's slots, tagging each with its day.

    Args:
        template: A template from this library.

    Returns:
        Every slot, each with a ``day_name`` key added.
    """
    return [{**slot, "day_name": day["name"]} for day in template["days"] for slot in day["slots"]]


__all__ = ["TEMPLATES", "get_template", "iter_slots", "query_templates"]
