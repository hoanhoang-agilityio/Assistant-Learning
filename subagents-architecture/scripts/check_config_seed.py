"""Validate ``data/rubric_seed.json`` and ``data/template_seed.json``.

These two files used to live inside ``app/core/langgraph/`` and were parsed at
import, which meant their invariants were enforced by the interpreter: a rubric
set that disagreed on ``rubric_version``, or two templates sharing a
``slot_id``, raised before the process could serve a request. Moving them into
Postgres removes that guarantee — nothing about a ``SELECT`` notices a
duplicate slot id — so the checks move here, in front of the seeder.

Run this *before* seeding, not after. The failures it catches are the silent
kind:

* Two templates sharing a ``slot_id`` make ``choose_exercises`` apply one
  model choice to two slots. The plan assembles, passes verification, and is
  simply not the plan the template describes.
* A rubric set that disagrees on ``rubric_version`` produces verify reports
  stamped with a version that only partly describes the rules that ran, and
  ``plan_versions.rubric_version`` can no longer reproduce an old verdict.
* A slot naming a movement pattern the taxonomy does not define can never be
  filled: ``filter_candidates`` matches ``movement_pattern`` exactly, so the
  slot yields no candidates and the build reports a conflicting constraint the
  user cannot act on.

Run::

    uv run python scripts/check_config_seed.py
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.movement_taxonomy import MOVEMENT_ATTRIBUTES  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_RUBRIC_SEED = _ROOT / "data" / "rubric_seed.json"
_TEMPLATE_SEED = _ROOT / "data" / "template_seed.json"

# The three rubrics the verifiers read. Named explicitly rather than accepting
# whatever the file happens to contain: a missing one would not raise at seed
# time, it would raise on the first plan that reaches that check.
_REQUIRED_RUBRICS = ("macro_rules", "volume_landmarks", "contraindications")

_TEMPLATE_KEYS = ("template_id", "name", "days_per_week", "goal", "level", "popularity", "days")
_SLOT_KEYS = ("slot_id", "pattern", "sets", "reps", "rir")


def validate_rubrics(rubrics: dict[str, Any]) -> list[str]:
    """Check the rubric seed.

    Args:
        rubrics: Parsed ``rubric_seed.json``, keyed by rubric name.

    Returns:
        Errors. Empty when the rubric set is seedable.
    """
    errors: list[str] = []

    missing = [name for name in _REQUIRED_RUBRICS if name not in rubrics]
    if missing:
        errors.append(f"missing rubrics {missing} — the verifiers read all three")

    unversioned = [name for name, body in rubrics.items() if not body.get("rubric_version")]
    if unversioned:
        errors.append(f"rubrics without a rubric_version: {sorted(unversioned)}")
        return errors

    versions = {body["rubric_version"] for body in rubrics.values()}
    if len(versions) != 1:
        errors.append(
            f"rubric versions disagree: {sorted(versions)}. A stored report cites one version, "
            "so all three must move together or the verdict cannot be reproduced."
        )

    contraindications = rubrics.get("contraindications", {})
    for injury, rule in contraindications.get("injuries", {}).items():
        if not rule.get("avoid_joint_actions"):
            errors.append(
                f"contraindications.{injury}: no avoid_joint_actions — the injury filter would "
                "intersect against nothing and screen nothing"
            )

    landmarks = rubrics.get("volume_landmarks", {})
    for muscle, entry in landmarks.get("muscles", {}).items():
        low, high = entry.get("mav", [0, 0])
        if not entry["mev"] <= low <= high <= entry["mrv"]:
            errors.append(
                f"volume_landmarks.{muscle}: expected mev <= mav[0] <= mav[1] <= mrv, "
                f"got mev={entry['mev']} mav={entry.get('mav')} mrv={entry['mrv']}"
            )

    return errors


def validate_templates(templates: list[dict[str, Any]]) -> list[str]:
    """Check the template seed.

    Args:
        templates: Parsed ``template_seed.json``.

    Returns:
        Errors. Empty when the library is seedable.
    """
    errors: list[str] = []

    duplicate_ids = [
        key for key, count in Counter(t.get("template_id") for t in templates).items() if count > 1
    ]
    if duplicate_ids:
        errors.append(f"duplicate template_ids (the table's primary key): {duplicate_ids}")

    # slot_id is the key the LLM returns its exercise choice against, so it must
    # be unique across the whole library, not merely within one template.
    seen_slots: dict[str, str] = {}

    for template in templates:
        template_id = template.get("template_id", "<no template_id>")

        missing = [key for key in _TEMPLATE_KEYS if key not in template]
        if missing:
            errors.append(f"{template_id}: missing keys {missing}")
            continue

        if not template["goal"]:
            errors.append(f"{template_id}: empty goal — query_templates can never match it")
        if not template["level"]:
            errors.append(f"{template_id}: empty level — query_templates can never match it")

        days = template["days"]
        if len(days) != template["days_per_week"]:
            errors.append(
                f"{template_id}: days_per_week={template['days_per_week']} but {len(days)} days "
                "defined. query_templates matches on the number, the plan is built from the list."
            )

        for day in days:
            for slot in day["slots"]:
                slot_id = slot.get("slot_id", "<no slot_id>")

                slot_missing = [key for key in _SLOT_KEYS if key not in slot]
                if slot_missing:
                    errors.append(f"{template_id}/{slot_id}: missing keys {slot_missing}")
                    continue

                owner = seen_slots.get(slot_id)
                if owner is not None:
                    errors.append(
                        f"duplicate slot_id '{slot_id}' in '{template_id}' and '{owner}' — one "
                        "exercise choice would silently fill both slots"
                    )
                seen_slots[slot_id] = template_id

                if slot["pattern"] not in MOVEMENT_ATTRIBUTES:
                    errors.append(
                        f"{template_id}/{slot_id}: pattern '{slot['pattern']}' has no taxonomy "
                        "entry, so no catalog exercise can ever fill this slot"
                    )

                if slot["sets"] < 1:
                    errors.append(f"{template_id}/{slot_id}: sets={slot['sets']}")
                for field in ("reps", "rir"):
                    low, high = slot[field]
                    if low > high:
                        errors.append(f"{template_id}/{slot_id}: {field}={slot[field]} is reversed")

    return errors


def main() -> int:
    """Validate both seed files.

    Returns:
        Process exit code: 0 when both are seedable, 1 otherwise.
    """
    for path in (_RUBRIC_SEED, _TEMPLATE_SEED):
        if not path.exists():
            print(f"missing seed file: {path}", file=sys.stderr)
            return 1

    rubrics = json.loads(_RUBRIC_SEED.read_text(encoding="utf-8"))
    templates = json.loads(_TEMPLATE_SEED.read_text(encoding="utf-8"))

    errors = validate_rubrics(rubrics) + validate_templates(templates)
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    slot_count = sum(len(day["slots"]) for t in templates for day in t.get("days", []))
    print(
        f"\n{len(rubrics)} rubrics · {len(templates)} templates · {slot_count} slots · "
        f"{len(errors)} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
