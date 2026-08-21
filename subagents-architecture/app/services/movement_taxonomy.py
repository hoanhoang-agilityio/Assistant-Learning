"""Movement pattern → biomechanical attributes.

One reviewable table instead of the same three fields repeated across every
catalog row. It exists because those three fields are what the safety checks
actually match on, and getting them wrong fails *silently*:

* ``joint_actions`` and ``loaded_positions`` are intersected with the
  contraindication rubric. If they carry a value the rubric never names — a
  constant like ``"compound"`` — the intersection is always empty and every
  injury check passes. Nothing errors; plans are simply never screened.
* ``contribution`` is what the volume check multiplies sets by. A leg curl
  credited to quads makes a hamstring day trip the quads MRV block while
  hamstrings register zero.

This table is now a **source of defaults and a validation vocabulary**, not the
authority. ``data/exercise_seed.json`` has been reviewed by hand and its values
win: ``scripts/check_exercise_seed.py`` fills these fields only for rows that
lack them, and never overwrites one that is present. Reviewed judgment beats a
pattern-level default — a Bulgarian split squat is harder than the ``lunge``
default implies, and a back extension is less fatiguing than the ``hinge``
default, because that base was calibrated for deadlifts.

The defaults stay deliberately conservative for the rows that do use them: a
pattern that loads a joint through deep range marks every exercise in it as
doing so, which over-excludes rather than under-excludes.

Vocabulary note: ``joint_actions`` values must be drawn from the same vocabulary
the contraindication rubric uses, or a rule can never fire. That coupling is
enforced by ``tests/test_app_catalog_data.py``, not by convention.
"""

from typing import TypedDict


class MovementAttributes(TypedDict):
    """Attributes shared by every exercise in one movement pattern."""

    joint_actions: list[str]
    loaded_positions: list[str]
    contribution: dict[str, float]
    # Difficulty and recovery cost of the pattern before equipment is
    # considered. `filter_candidates` gates on skill and sorts by fatigue, so
    # both are load-bearing rather than descriptive.
    base_skill_level: int
    base_fatigue_cost: int


# Keyed by movement_pattern. Every pattern present in the catalog needs an entry;
# a missing one is caught by the catalog data tests rather than defaulting to
# something permissive.
MOVEMENT_ATTRIBUTES: dict[str, MovementAttributes] = {
    # --- lower body -------------------------------------------------------
    "squat": {
        "joint_actions": ["knee_flexion_deep", "knee_extension", "hip_extension"],
        "loaded_positions": ["knee_end_range"],
        "contribution": {"quads": 1.0, "glutes": 0.5, "hamstrings": 0.3},
        "base_skill_level": 3,
        "base_fatigue_cost": 5,
    },
    "lunge": {
        # Deliberately NOT `knee_flexion_deep`. The contraindication rubric caps
        # the lunge pattern at 4 sets/week for patellofemoral pain rather than
        # banning it — and a joint action that excludes the pattern outright
        # makes that limit rule unreachable. Capping is the rubric's stated
        # intent, so the attributes must leave lunges selectable.
        "joint_actions": ["knee_flexion", "knee_extension", "hip_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 0.8, "glutes": 0.8, "hamstrings": 0.3},
        "base_skill_level": 2,
        "base_fatigue_cost": 4,
    },
    "knee_extension": {
        "joint_actions": ["knee_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "knee_flexion": {
        "joint_actions": ["knee_flexion"],
        "loaded_positions": [],
        "contribution": {"hamstrings": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "hinge": {
        "joint_actions": ["hip_extension", "spinal_stabilization"],
        "loaded_positions": [],
        "contribution": {"hamstrings": 1.0, "glutes": 0.8},
        "base_skill_level": 3,
        "base_fatigue_cost": 5,
    },
    "hip_thrust": {
        "joint_actions": ["hip_extension"],
        "loaded_positions": [],
        "contribution": {"glutes": 1.0, "hamstrings": 0.4},
        "base_skill_level": 2,
        "base_fatigue_cost": 3,
    },
    "hip_flexion": {
        "joint_actions": ["hip_flexion"],
        "loaded_positions": [],
        "contribution": {"abs": 0.5, "quads": 0.3},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "calf_raise": {
        "joint_actions": ["ankle_plantarflexion"],
        "loaded_positions": [],
        "contribution": {"calves": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    # --- horizontal press / pull -----------------------------------------
    "horizontal_push": {
        "joint_actions": ["shoulder_horizontal_adduction", "elbow_extension"],
        "loaded_positions": [],
        "contribution": {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
        "base_skill_level": 2,
        "base_fatigue_cost": 4,
    },
    "angled_push": {
        "joint_actions": ["shoulder_horizontal_adduction", "elbow_extension"],
        "loaded_positions": [],
        "contribution": {"chest": 0.8, "front_delts": 0.8, "triceps": 0.5},
        "base_skill_level": 2,
        "base_fatigue_cost": 3,
    },
    "horizontal_adduction": {
        # A fly takes the shoulder into external rotation at end range under
        # load, which is the position the impingement rule names.
        "joint_actions": ["shoulder_horizontal_adduction"],
        "loaded_positions": ["shoulder_end_range_external"],
        "contribution": {"chest": 1.0, "front_delts": 0.3},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "horizontal_pull": {
        "joint_actions": ["shoulder_horizontal_abduction", "elbow_flexion"],
        "loaded_positions": [],
        "contribution": {"lats": 0.8, "rear_delts": 0.5, "biceps": 0.5},
        "base_skill_level": 2,
        "base_fatigue_cost": 3,
    },
    "rear_delt_pull": {
        "joint_actions": ["shoulder_horizontal_abduction"],
        "loaded_positions": [],
        "contribution": {"rear_delts": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    # --- vertical press / pull -------------------------------------------
    "vertical_push": {
        "joint_actions": ["shoulder_abduction_overhead", "elbow_extension"],
        "loaded_positions": ["shoulder_end_range_external"],
        "contribution": {"front_delts": 1.0, "side_delts": 0.5, "triceps": 0.5},
        "base_skill_level": 3,
        "base_fatigue_cost": 4,
    },
    "vertical_pull": {
        "joint_actions": ["shoulder_adduction", "elbow_flexion"],
        "loaded_positions": [],
        "contribution": {"lats": 1.0, "biceps": 0.5, "rear_delts": 0.3},
        "base_skill_level": 2,
        "base_fatigue_cost": 3,
    },
    "high_pull": {
        "joint_actions": ["shoulder_abduction_overhead", "elbow_flexion"],
        "loaded_positions": [],
        "contribution": {"side_delts": 0.8, "rear_delts": 0.5},
        "base_skill_level": 3,
        "base_fatigue_cost": 3,
    },
    "abduction": {
        # A lateral raise to shoulder height is not overhead abduction, so it is
        # deliberately NOT flagged for impingement. Raising the arm past
        # shoulder height would be, and belongs in a separate pattern.
        "joint_actions": ["shoulder_abduction"],
        "loaded_positions": [],
        "contribution": {"side_delts": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "shoulder_extension": {
        "joint_actions": ["shoulder_extension"],
        "loaded_positions": [],
        "contribution": {"lats": 0.8, "triceps": 0.3},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "scapular": {
        "joint_actions": ["scapular_retraction"],
        "loaded_positions": [],
        "contribution": {"rear_delts": 0.5, "lats": 0.3},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "dip": {
        "joint_actions": ["shoulder_extension", "elbow_extension"],
        "loaded_positions": ["shoulder_end_range_external"],
        "contribution": {"triceps": 1.0, "chest": 0.8, "front_delts": 0.5},
        "base_skill_level": 3,
        "base_fatigue_cost": 3,
    },
    # --- arms -------------------------------------------------------------
    "elbow_flexion": {
        "joint_actions": ["elbow_flexion"],
        "loaded_positions": [],
        "contribution": {"biceps": 1.0, "forearms": 0.3},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "elbow_extension": {
        "joint_actions": ["elbow_extension"],
        "loaded_positions": [],
        "contribution": {"triceps": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    # --- trunk ------------------------------------------------------------
    "anti_extension": {
        "joint_actions": ["spinal_stabilization"],
        "loaded_positions": [],
        "contribution": {"abs": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
    "anti_rotation": {
        "joint_actions": ["spinal_stabilization"],
        "loaded_positions": [],
        "contribution": {"obliques": 1.0, "abs": 0.5},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "anti_lateral_flexion": {
        "joint_actions": ["spinal_stabilization"],
        "loaded_positions": [],
        "contribution": {"obliques": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "trunk_flexion": {
        "joint_actions": ["spinal_flexion"],
        "loaded_positions": [],
        "contribution": {"abs": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "flexion": {
        "joint_actions": ["spinal_flexion"],
        "loaded_positions": [],
        "contribution": {"abs": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 1,
    },
    "rotation": {
        "joint_actions": ["spinal_rotation"],
        "loaded_positions": [],
        "contribution": {"obliques": 1.0},
        "base_skill_level": 1,
        "base_fatigue_cost": 2,
    },
}


# How much each implement adds to or removes from the pattern's base skill
# level. A machine constrains the path and removes the balance demand; a barbell
# adds both. Fatigue cost is left to the pattern — what tires you is the muscle
# mass and range involved, not the implement.
_EQUIPMENT_SKILL_MODIFIER: dict[str, int] = {
    "machine": -1,
    "cable": -1,
    "smith_machine": -1,
    "resistance_band": -1,
    "dumbbell": 0,
    "kettlebell": 0,
    "bodyweight": 0,
    "ez_bar": 0,
    "barbell": 1,
    "pull_up_bar": 1,
    "dip_station": 1,
}

_MIN_SKILL_LEVEL = 1
_MAX_SKILL_LEVEL = 5


def skill_level_for(movement_pattern: str, equipment: list[str]) -> int:
    """Derive an exercise's skill level from its pattern and implement.

    ``filter_candidates`` excludes anything above the user's level, so this
    decides what a beginner is offered. It replaces round-robin placeholder
    values that rated a machine leg extension harder than a barbell squat.

    Args:
        movement_pattern: The exercise's movement pattern.
        equipment: The equipment it requires.

    Returns:
        A level clamped to 1–5.

    Raises:
        KeyError: When the pattern has no taxonomy entry.
    """
    base = attributes_for(movement_pattern)["base_skill_level"]
    modifier = max((_EQUIPMENT_SKILL_MODIFIER.get(item, 0) for item in equipment), default=0)
    return max(_MIN_SKILL_LEVEL, min(_MAX_SKILL_LEVEL, base + modifier))


def fatigue_cost_for(movement_pattern: str) -> int:
    """Derive an exercise's recovery cost from its movement pattern.

    ``filter_candidates`` sorts candidates by this, so it decides which option a
    tie resolves toward.

    Args:
        movement_pattern: The exercise's movement pattern.

    Returns:
        A cost from 1 to 5.

    Raises:
        KeyError: When the pattern has no taxonomy entry.
    """
    return attributes_for(movement_pattern)["base_fatigue_cost"]


def attributes_for(movement_pattern: str) -> MovementAttributes:
    """Return the attributes for a movement pattern.

    Args:
        movement_pattern: The pattern to look up.

    Returns:
        Its joint actions, loaded positions and muscle contributions.

    Raises:
        KeyError: When the pattern has no entry. Deliberately not defaulting:
            an unmapped pattern would silently receive no joint actions, which
            makes every injury rule pass for those exercises.
    """
    if movement_pattern not in MOVEMENT_ATTRIBUTES:
        raise KeyError(
            f"movement_pattern {movement_pattern!r} has no taxonomy entry. "
            "Add one — an unmapped pattern is invisible to the injury checks."
        )
    return MOVEMENT_ATTRIBUTES[movement_pattern]


__all__ = [
    "MOVEMENT_ATTRIBUTES",
    "MovementAttributes",
    "attributes_for",
    "fatigue_cost_for",
    "skill_level_for",
]
