"""Rubrics and templates as the tests read them: straight from the seed files.

The application reads these from Postgres. The tests read the same content from
``data/rubric_seed.json`` and ``data/template_seed.json``, which is what
``scripts/seed_config.py`` loads — so the two cannot drift without the seeder
having been skipped.

Reading the files rather than calling ``app.services.rubrics`` keeps the suite
runnable without a database. Every test that uses these is asserting something
about the *rules* — that a template's slots are fillable, that the injury rubric
names actions the catalog uses — and none of that is a claim about storage.
"""

import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"

RUBRICS: dict[str, Any] = json.loads((_DATA / "rubric_seed.json").read_text(encoding="utf-8"))

MACRO_RULES: dict[str, Any] = RUBRICS["macro_rules"]
VOLUME_LANDMARKS: dict[str, Any] = RUBRICS["volume_landmarks"]
CONTRAINDICATIONS: dict[str, Any] = RUBRICS["contraindications"]
RUBRIC_VERSION: str = MACRO_RULES["rubric_version"]

TEMPLATES: dict[str, dict[str, Any]] = {
    entry["template_id"]: entry
    for entry in json.loads((_DATA / "template_seed.json").read_text(encoding="utf-8"))
}


def query_templates(
    days_per_week: int, goal: str, level: int, limit: int = 3
) -> list[dict[str, Any]]:
    """Mirror ``app.services.templates.query_templates`` over the seed file.

    Args:
        days_per_week: Sessions the user can train.
        goal: Training goal.
        level: Experience level.
        limit: Maximum templates to return.

    Returns:
        Matching templates, most popular first.
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
    """Return one template from the seed file.

    Args:
        template_id: The template's id.

    Returns:
        The template, or ``None``.
    """
    return TEMPLATES.get(template_id)


__all__ = [
    "CONTRAINDICATIONS",
    "MACRO_RULES",
    "RUBRICS",
    "RUBRIC_VERSION",
    "TEMPLATES",
    "VOLUME_LANDMARKS",
    "get_template",
    "query_templates",
]
