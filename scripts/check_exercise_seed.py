"""Validate ``data/exercise_seed.json``.

**This script does not rewrite reviewed values.** It replaces
``normalize_exercise_seed.py``, which derived ``joint_actions``,
``loaded_positions``, ``contribution``, ``skill_level`` and ``fatigue_cost``
from the movement taxonomy and overwrote whatever was in the file. That was the
right tool for the raw seed, where those fields were constants and copy-paste.
It is the wrong tool now: the catalog has been reviewed by hand, and re-running
the old script would silently revert every correction.

The name changed with the behaviour on purpose. "Normalize" reads as *this
rewrites the file*, and someone remembering it as safe to run would have been
right yesterday and wrong today.

Two modes::

    uv run python scripts/check_exercise_seed.py           # validate, write nothing
    uv run python scripts/check_exercise_seed.py --fill    # add MISSING fields only

``--fill`` exists for newly added rows: give an entry an ``id``, ``name``,
``movement_pattern`` and ``equipment``, and it derives the rest from
``app/services/movement_taxonomy.py``. It never changes a value that is already
present, so running it can only ever add information.

The checks below are not stylistic. The original seed shipped
``joint_actions: ["compound"]`` on every row — a value the contraindication
rubric never names — so every injury screen intersected against nothing and
silently passed. A typo in one of those fields reproduces that failure for one
exercise, and nothing at runtime would report it.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.langgraph.rubrics import CONTRAINDICATIONS  # noqa: E402
from app.services.movement_taxonomy import (  # noqa: E402
    MOVEMENT_ATTRIBUTES,
    attributes_for,
    fatigue_cost_for,
    skill_level_for,
)

_ROOT = Path(__file__).resolve().parent.parent
_SEED = _ROOT / "data" / "exercise_seed.json"

_REQUIRED_KEYS = (
    "id",
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

_MIN_LEVEL, _MAX_LEVEL = 1, 5


def _known_joint_actions() -> set[str]:
    """Every joint action the system recognises.

    Union of what the taxonomy assigns and what the contraindication rubric
    forbids. A value outside this set can never match a rule, so it is almost
    always a typo — and an invisible one.

    Returns:
        The recognised joint actions.
    """
    from_taxonomy = {
        action for entry in MOVEMENT_ATTRIBUTES.values() for action in entry["joint_actions"]
    }
    from_rubric = {
        action
        for injury in CONTRAINDICATIONS["injuries"].values()
        for action in injury["avoid_joint_actions"]
    }
    return from_taxonomy | from_rubric


def _known_loaded_positions() -> set[str]:
    """Every loaded position the system recognises.

    Returns:
        The recognised loaded positions.
    """
    from_taxonomy = {
        position for entry in MOVEMENT_ATTRIBUTES.values() for position in entry["loaded_positions"]
    }
    from_rubric = {
        position
        for injury in CONTRAINDICATIONS["injuries"].values()
        for position in injury.get("avoid_loaded_positions", [])
    }
    return from_taxonomy | from_rubric


def validate(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Check the catalog for problems.

    Args:
        rows: The seed file's contents.

    Returns:
        ``(errors, warnings)``. Errors make the catalog unusable; warnings are
        values that look like typos but might be deliberate.
    """
    errors: list[str] = []
    warnings: list[str] = []

    duplicates = [key for key, count in Counter(r.get("id") for r in rows).items() if count > 1]
    if duplicates:
        errors.append(f"duplicate ids (the table's primary key): {duplicates}")

    known_actions = _known_joint_actions()
    known_positions = _known_loaded_positions()

    for row in rows:
        exercise_id = row.get("id", "<no id>")

        missing = [key for key in _REQUIRED_KEYS if key not in row]
        if missing:
            errors.append(f"{exercise_id}: missing keys {missing}")
            continue

        pattern = row["movement_pattern"]
        if pattern not in MOVEMENT_ATTRIBUTES:
            errors.append(
                f"{exercise_id}: movement_pattern '{pattern}' has no taxonomy entry, so "
                "nothing can derive or validate its attributes"
            )

        if not row["contribution"]:
            errors.append(f"{exercise_id}: empty contribution — contributes to no muscle's volume")
        for muscle, share in row["contribution"].items():
            if not 0 < share <= 1.0:
                errors.append(
                    f"{exercise_id}: contribution['{muscle}'] = {share}, expected 0 < s <= 1"
                )

        for field, bound in (("skill_level", _MAX_LEVEL), ("fatigue_cost", _MAX_LEVEL)):
            value = row[field]
            if not isinstance(value, int) or not _MIN_LEVEL <= value <= bound:
                errors.append(f"{exercise_id}: {field} = {value!r}, expected {_MIN_LEVEL}-{bound}")

        if not row["equipment"]:
            errors.append(f"{exercise_id}: empty equipment — no profile can ever match it")

        unknown_actions = set(row["joint_actions"]) - known_actions
        if unknown_actions:
            warnings.append(
                f"{exercise_id}: joint_actions {sorted(unknown_actions)} match no taxonomy entry "
                "and no rubric rule — a typo here disables injury screening for this exercise"
            )

        unknown_positions = set(row["loaded_positions"]) - known_positions
        if unknown_positions:
            warnings.append(
                f"{exercise_id}: loaded_positions {sorted(unknown_positions)} match no rule"
            )

    return errors, warnings


def fill_missing(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Add absent fields to rows that lack them, changing nothing else.

    Args:
        rows: The seed file's contents.

    Returns:
        ``(rows, filled)`` where ``filled`` describes what was added.
    """
    filled: list[str] = []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        exercise_id = row.get("id")
        if not exercise_id or exercise_id in seen:
            filled.append(f"{exercise_id}: dropped as a duplicate")
            continue
        seen.add(exercise_id)

        entry = dict(row)
        pattern = entry.get("movement_pattern")
        if pattern not in MOVEMENT_ATTRIBUTES:
            result.append(entry)
            continue

        attributes = attributes_for(pattern)
        added: list[str] = []

        def fill(field: str, default: Any) -> None:
            """Set a field only when its key is absent.

            Absence, not emptiness, is what "missing" means here. An empty list
            is a real answer for several of these — a scapular raise has no
            muscle at a full share, so ``primary_muscles: []`` is correct, and
            treating it as unset would report a change that never happened.
            A tool whose entire purpose is not touching reviewed data must not
            claim edits it did not make.
            """
            if field not in entry:
                entry[field] = default
                added.append(field)

        fill("joint_actions", list(attributes["joint_actions"]))
        fill("loaded_positions", list(attributes["loaded_positions"]))
        fill("contribution", dict(attributes["contribution"]))

        contribution = entry.get("contribution") or {}
        fill("primary_muscles", sorted(m for m, s in contribution.items() if s >= 1.0))
        fill("secondary_muscles", sorted(m for m, s in contribution.items() if s < 1.0))
        fill("equipment", ["machine"])
        fill("skill_level", skill_level_for(pattern, entry.get("equipment") or ["machine"]))
        fill("fatigue_cost", fatigue_cost_for(pattern))

        if added:
            filled.append(f"{exercise_id}: filled {added}")
        result.append(entry)

    result.sort(key=lambda entry: entry["id"])
    return result, filled


def main() -> int:
    """Validate the seed file, optionally filling absent fields.

    Returns:
        Process exit code: 0 when the catalog is usable, 1 on errors.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fill",
        action="store_true",
        help="add missing fields to new rows. Never overwrites a value already present.",
    )
    args = parser.parse_args()

    if not _SEED.exists():
        print(f"missing seed file: {_SEED}", file=sys.stderr)
        return 1

    rows = json.loads(_SEED.read_text(encoding="utf-8"))

    if args.fill:
        rows, filled = fill_missing(rows)
        if filled:
            _SEED.write_text(
                json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"filled {len(filled)} rows:")
            for line in filled:
                print(f"  {line}")
        else:
            print("nothing to fill — every row is complete")

    errors, warnings = validate(rows)

    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    print(
        f"\n{len(rows)} exercises · {len({r['movement_pattern'] for r in rows})} patterns · "
        f"{len(errors)} errors · {len(warnings)} warnings"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
