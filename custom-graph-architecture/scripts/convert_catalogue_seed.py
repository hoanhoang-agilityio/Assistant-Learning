"""Conversion of the source catalogue seed into this repo's schema.

Kept in the repo because the mapping below is the auditable part: every field this project
needs that the source data did not carry is derived here, in one place, rather than hidden
inside a migration. Re-runnable — it validates its output against the domain models.

    uv run python scripts/convert_catalogue_seed.py [source-data-dir]

The source lives in ``data/source`` so this project seeds from its own copy rather than
from a sibling repo's working tree.
"""

import json
import sys
from pathlib import Path
from typing import Any

from src.enums import (
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    FitnessGoal,
    MovementPattern,
    MuscleGroup,
)
from src.schemas import (
    Exercise,
    WorkoutTemplate,
)

OUTPUT_DIR = Path("data")
SOURCE_DIR = Path("data/source")

# A plan prescribes sets and reps, and the gate rejects anything else in `reps`. A source
# row measured in seconds gives the agent no reps to write, so it writes "45-60s" and the
# plan fails verification three times over. Such a row has to be re-expressed as a
# repetition movement in the seed before it reaches the catalogue.
DURATION_KEYS = ("unit", "duration_seconds")

# The source names its own taxonomy in lower snake case. Every value maps onto a member of
# our enums; nothing is dropped and nothing is collapsed onto a shared bucket.
MUSCLES: dict[str, MuscleGroup] = {
    "abs": MuscleGroup.ABS,
    "biceps": MuscleGroup.BICEPS,
    "calves": MuscleGroup.CALVES,
    "chest": MuscleGroup.CHEST,
    "forearms": MuscleGroup.FOREARMS,
    "front_delts": MuscleGroup.FRONT_DELTS,
    "glutes": MuscleGroup.GLUTES,
    "hamstrings": MuscleGroup.HAMSTRINGS,
    "lats": MuscleGroup.LATS,
    "obliques": MuscleGroup.OBLIQUES,
    "quads": MuscleGroup.QUADS,
    "rear_delts": MuscleGroup.REAR_DELTS,
    "side_delts": MuscleGroup.SIDE_DELTS,
    "triceps": MuscleGroup.TRICEPS,
}

EQUIPMENT: dict[str, EquipmentType] = {
    "barbell": EquipmentType.BARBELL,
    "bodyweight": EquipmentType.BODYWEIGHT,
    "cable": EquipmentType.CABLE,
    "dip_station": EquipmentType.DIP_STATION,
    "dumbbell": EquipmentType.DUMBBELL,
    "kettlebell": EquipmentType.KETTLEBELL,
    "machine": EquipmentType.MACHINE,
    "pull_up_bar": EquipmentType.PULL_UP_BAR,
    "smith_machine": EquipmentType.SMITH_MACHINE,
}

GOALS: dict[str, FitnessGoal] = {
    "fat_loss": FitnessGoal.FAT_LOSS,
    "muscle_gain": FitnessGoal.MUSCLE_GAIN,
    # The source's "recomp" is simultaneous fat loss and muscle gain, which this project
    # models as maintaining weight while training; "general_health" is its own goal.
    "recomp": FitnessGoal.MAINTENANCE,
    "general_health": FitnessGoal.GENERAL_FITNESS,
}

# Body region is not in the source. It follows from what a movement trains, so it is
# derived from the primary muscles rather than guessed per exercise.
REGION_BY_MUSCLE: dict[MuscleGroup, BodyRegion] = {
    MuscleGroup.CHEST: BodyRegion.UPPER,
    MuscleGroup.BACK: BodyRegion.UPPER,
    MuscleGroup.LATS: BodyRegion.UPPER,
    MuscleGroup.SHOULDERS: BodyRegion.UPPER,
    MuscleGroup.FRONT_DELTS: BodyRegion.UPPER,
    MuscleGroup.SIDE_DELTS: BodyRegion.UPPER,
    MuscleGroup.REAR_DELTS: BodyRegion.UPPER,
    MuscleGroup.BICEPS: BodyRegion.UPPER,
    MuscleGroup.TRICEPS: BodyRegion.UPPER,
    MuscleGroup.FOREARMS: BodyRegion.UPPER,
    MuscleGroup.QUADS: BodyRegion.LOWER,
    MuscleGroup.HAMSTRINGS: BodyRegion.LOWER,
    MuscleGroup.GLUTES: BodyRegion.LOWER,
    MuscleGroup.CALVES: BodyRegion.LOWER,
    MuscleGroup.HIP: BodyRegion.LOWER,
    MuscleGroup.ABS: BodyRegion.CORE,
    MuscleGroup.OBLIQUES: BodyRegion.CORE,
    MuscleGroup.LOWER_BACK: BodyRegion.CORE,
}

# The source grades skill 1-5; this project grades it in three bands.
DIFFICULTY_BY_SKILL: dict[int, DifficultyLevel] = {
    1: DifficultyLevel.BEGINNER,
    2: DifficultyLevel.BEGINNER,
    3: DifficultyLevel.INTERMEDIATE,
    4: DifficultyLevel.ADVANCED,
    5: DifficultyLevel.ADVANCED,
}


def _pattern(value: str) -> MovementPattern:
    """Map a source movement pattern onto this project's enum."""
    return MovementPattern(value.upper())


def _region(primary_muscles: list[MuscleGroup]) -> BodyRegion:
    """Derive an exercise's body region from the muscles it primarily trains."""
    regions = {REGION_BY_MUSCLE[muscle] for muscle in primary_muscles}
    if len(regions) == 1:
        return regions.pop()
    return BodyRegion.FULL_BODY


def _muscles(row: dict[str, Any]) -> tuple[list[MuscleGroup], list[MuscleGroup]]:
    """Split a row's muscles into primary and secondary.

    Twenty source rows list no primary muscle at all: the source treats a contribution of
    1.0 as primary, and those rows top out at 0.8. Their ``contribution`` map still ranks
    the muscles, so the most heavily weighted ones are taken as primary rather than
    dropping otherwise usable exercises.
    """
    if row["primary_muscles"]:
        return (
            [MUSCLES[name] for name in row["primary_muscles"]],
            [MUSCLES[name] for name in row["secondary_muscles"]],
        )

    contribution: dict[str, float] = row.get("contribution") or {}
    if not contribution:
        raise ValueError(f"{row['id']} has neither primary muscles nor contributions")

    highest = max(contribution.values())
    primary = [
        MUSCLES[name] for name, weight in contribution.items() if weight == highest
    ]
    secondary = [
        MUSCLES[name] for name, weight in contribution.items() if weight != highest
    ]
    return primary, secondary


def convert_exercise(row: dict[str, Any]) -> Exercise:
    """Convert one source exercise row.

    ``contraindications`` stays empty: the source carries none, and inventing which
    injuries rule a movement out is not a mapping decision. Injury filtering still works
    through the movement restrictions on the user's own profile.
    """
    primary, secondary = _muscles(row)
    return Exercise(
        id=row["id"],
        name=row["name"],
        body_region=_region(primary),
        primary_muscles=primary,
        secondary_muscles=secondary,
        movement_pattern=_pattern(row["movement_pattern"]),
        difficulty=DIFFICULTY_BY_SKILL[row["skill_level"]],
        equipment=[EQUIPMENT[name] for name in row["equipment"]],
    )


def _day_region(
    slots: list[dict[str, Any]], exercises: dict[str, Exercise]
) -> BodyRegion:
    """Derive a training day's region from the regions its slots can be filled from."""
    regions = set()
    for slot in slots:
        pattern = _pattern(slot["pattern"])
        regions.update(
            exercise.body_region
            for exercise in exercises.values()
            if exercise.movement_pattern is pattern
        )
    non_core = regions - {BodyRegion.CORE}
    if len(non_core) == 1:
        return non_core.pop()
    return BodyRegion.FULL_BODY


def convert_template(
    row: dict[str, Any], exercises: dict[str, Exercise]
) -> WorkoutTemplate:
    """Convert one source template, carrying its prescribed volume onto the slots."""
    return WorkoutTemplate(
        id=row["template_id"],
        name=row["name"],
        goals=[GOALS[goal] for goal in row["goal"]],
        popularity=row.get("popularity", 0),
        training_days=[
            {
                "day_number": number,
                "name": day["name"],
                "body_region": _day_region(day["slots"], exercises),
                "exercise_slots": [
                    {
                        "slot_id": slot["slot_id"],
                        "allowed_movement_patterns": [_pattern(slot["pattern"])],
                        "sets": slot.get("sets"),
                        "rep_range": slot.get("reps"),
                        "rir_range": slot.get("rir"),
                    }
                    for slot in day["slots"]
                ],
            }
            for number, day in enumerate(row["days"], start=1)
        ],
    )


def reject_duration_rows(rows: list[dict[str, Any]]) -> None:
    """Refuse a seed the coach agent could only prescribe in seconds."""

    timed = [row["id"] for row in rows if any(key in row for key in DURATION_KEYS)]
    if timed:
        raise ValueError(
            f"{len(timed)} source rows are measured in time, not repetitions: "
            f"{', '.join(timed)}. Re-express them as repetition movements in "
            f"{SOURCE_DIR / 'exercise_seed.json'} before converting."
        )


def main(source_dir: Path = SOURCE_DIR) -> None:
    """Convert both seed files and write them into this repo's ``data/`` directory."""
    source_exercises = json.loads((source_dir / "exercise_seed.json").read_text())
    source_templates = json.loads((source_dir / "template_seed.json").read_text())

    reject_duration_rows(source_exercises)

    exercises = {row["id"]: convert_exercise(row) for row in source_exercises}
    templates = [convert_template(row, exercises) for row in source_templates]

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "exercises.json").write_text(
        json.dumps(
            [exercise.model_dump(mode="json") for exercise in exercises.values()],
            indent=2,
        )
        + "\n"
    )
    (OUTPUT_DIR / "templates.json").write_text(
        json.dumps(
            [template.model_dump(mode="json") for template in templates], indent=2
        )
        + "\n"
    )
    print(f"wrote {len(exercises)} exercises and {len(templates)} templates")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE_DIR)
