"""Canonical movement-pattern taxonomy and exercise candidate pools.

Deterministic exercise selection depends on a fixed, equipment-scoped candidate
list per movement pattern rather than a free-text name invented by an LLM. Every
exercise name that can ever appear in a generated workout originates here.
"""

from typing import Literal

from core.profile.schema import Equipment

MovementPattern = Literal[
    "horizontal_push",
    "horizontal_pull",
    "vertical_push",
    "vertical_pull",
    "squat",
    "hinge",
    "lunge",
    "core",
    "lateral_raise",
    "rear_delt",
    "isolation_arms",
    "calves",
    "full_body",
]

ExerciseType = Literal["compound", "isolation"]

EXERCISE_TYPE_BY_PATTERN: dict[MovementPattern, ExerciseType] = {
    "horizontal_push": "compound",
    "horizontal_pull": "compound",
    "vertical_push": "compound",
    "vertical_pull": "compound",
    "squat": "compound",
    "hinge": "compound",
    "lunge": "compound",
    "core": "isolation",
    "lateral_raise": "isolation",
    "rear_delt": "isolation",
    "isolation_arms": "isolation",
    "calves": "isolation",
    "full_body": "compound",
}

# Base candidate pool per (movement_pattern, equipment). Ordering is deliberate:
# it's the deterministic fallback order exercise_rules.py uses when no
# preference rule uniquely matches (see exercise_rules.RESOLUTION_RULES).
EXERCISE_POOL: dict[tuple[MovementPattern, Equipment], tuple[str, ...]] = {
    ("horizontal_push", "gym"): ("Bench Press", "Incline Dumbbell Press", "Machine Chest Press"),
    ("horizontal_push", "home"): ("Dumbbell Bench Press", "Push-up", "Incline Push-up"),
    ("horizontal_push", "bodyweight"): ("Push-up", "Incline Push-up", "Diamond Push-up"),
    ("horizontal_pull", "gym"): ("Barbell Row", "Seated Cable Row", "Chest-Supported Row"),
    ("horizontal_pull", "home"): ("Dumbbell Row", "Resistance Band Row"),
    ("horizontal_pull", "bodyweight"): ("Inverted Row", "Towel Row"),
    ("vertical_push", "gym"): (
        "Overhead Press",
        "Machine Shoulder Press",
        "Dumbbell Shoulder Press",
    ),
    ("vertical_push", "home"): ("Dumbbell Shoulder Press", "Pike Push-up"),
    ("vertical_push", "bodyweight"): ("Pike Push-up", "Handstand Hold Press"),
    ("vertical_pull", "gym"): ("Lat Pulldown", "Pull-up", "Assisted Pull-up"),
    ("vertical_pull", "home"): ("Resistance Band Pulldown", "Doorway Row"),
    ("vertical_pull", "bodyweight"): ("Pull-up", "Chin-up"),
    ("squat", "gym"): ("Back Squat", "Leg Press", "Goblet Squat"),
    ("squat", "home"): ("Goblet Squat", "Dumbbell Squat"),
    ("squat", "bodyweight"): ("Bodyweight Squat", "Jump Squat", "Bulgarian Split Squat"),
    ("hinge", "gym"): ("Romanian Deadlift", "Deadlift", "Hip Thrust"),
    ("hinge", "home"): ("Dumbbell Romanian Deadlift", "Single-Leg Hip Thrust"),
    ("hinge", "bodyweight"): ("Glute Bridge", "Single-Leg Romanian Deadlift"),
    ("lunge", "gym"): ("Walking Lunge", "Bulgarian Split Squat", "Step-up"),
    ("lunge", "home"): ("Dumbbell Walking Lunge", "Reverse Lunge"),
    ("lunge", "bodyweight"): ("Walking Lunge", "Reverse Lunge"),
    ("core", "gym"): ("Cable Crunch", "Hanging Leg Raise", "Ab Wheel Rollout"),
    ("core", "home"): ("Plank", "Dead Bug"),
    ("core", "bodyweight"): ("Plank", "Sit-up", "Mountain Climber"),
    ("lateral_raise", "gym"): ("Lateral Raise", "Cable Lateral Raise"),
    ("lateral_raise", "home"): ("Dumbbell Lateral Raise",),
    ("lateral_raise", "bodyweight"): ("Band Lateral Raise",),
    ("rear_delt", "gym"): ("Face Pull", "Reverse Fly", "Cable Face Pull"),
    ("rear_delt", "home"): ("Band Face Pull", "Dumbbell Reverse Fly"),
    ("rear_delt", "bodyweight"): ("Band Face Pull", "Prone Y Raise"),
    ("isolation_arms", "gym"): ("Triceps Pushdown", "Biceps Curl", "Cable Curl"),
    ("isolation_arms", "home"): ("Dumbbell Curl", "Overhead Triceps Extension"),
    ("isolation_arms", "bodyweight"): ("Diamond Push-up", "Chair Dip"),
    ("calves", "gym"): ("Standing Calf Raise", "Seated Calf Raise"),
    ("calves", "home"): ("Dumbbell Calf Raise",),
    ("calves", "bodyweight"): ("Calf Raise",),
    ("full_body", "gym"): ("Goblet Squat", "Push-up", "Romanian Deadlift", "Row"),
    ("full_body", "home"): (
        "Goblet Squat",
        "Push-up",
        "Dumbbell Romanian Deadlift",
        "Dumbbell Row",
    ),
    ("full_body", "bodyweight"): ("Bodyweight Squat", "Push-up", "Glute Bridge", "Inverted Row"),
}


def candidates_for_slot(
    pattern: MovementPattern,
    equipment: Equipment,
    *,
    exclude_names: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Deterministic candidate exercises for a movement-pattern slot.

    `exclude_names` removes exercises already placed elsewhere in the plan (or,
    during repair, an exercise that already failed validation) -- comparison is
    case-insensitive since exercise names flow through user-facing text.
    """
    pool = EXERCISE_POOL[(pattern, equipment)]
    if not exclude_names:
        return pool
    excluded_lower = {name.strip().lower() for name in exclude_names}
    return tuple(name for name in pool if name.strip().lower() not in excluded_lower)


def exercise_type_for(pattern: MovementPattern) -> ExerciseType:
    """Whether a movement pattern is a compound or isolation exercise, for the
    Volume/Rep Engines' lookup key."""
    return EXERCISE_TYPE_BY_PATTERN[pattern]
