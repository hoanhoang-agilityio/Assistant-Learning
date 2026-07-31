"""Backwards-compatible re-exports for the old fitness.utils module.

This file used to hold 828 lines: BMR/TDEE arithmetic, the calorie floors and
protein ceiling, workout safety validation, plan synthesis, deterministic edit
operations and VFS writes -- all under a name that told readers there was
nothing important inside. The logic now lives in modules named after what it
does:

    constants.py    the named safety-relevant numbers (floors, ceilings, caps)
    context.py      loading profile / plan / research evidence from the VFS
    macros.py       BMR, TDEE, macro targets, weekly-set counting
    safety.py       macro bounds, equipment mismatch, unsafe markup, feedback
    synthesis.py    assembling the final plan text and workout summary
    artifacts.py    persisting fitness results to the VFS
    edit_ops.py     default templates, day-count fixes, exercise replacement

Nothing was rewritten in the move and no constant value changed. This shim
exists so existing importers keep working; prefer importing from the modules
above in new code.
"""

from core.capabilities.fitness.artifacts import write_fitness_artifacts
from core.capabilities.fitness.constants import (
    ACTIVITY_MULTIPLIERS,
    BODYWEIGHT_GYM_KEYWORDS,
    DEFAULT_ACTIVITY_MULTIPLIER,
    HOME_GYM_KEYWORDS,
    MAX_CALORIES,
    MAX_EXERCISE_SETS,
    MAX_PROTEIN_G_PER_KG,
    MAX_TRAINING_DAYS,
    MAX_WEEKLY_SETS,
    MIN_CALORIES_FEMALE,
    MIN_CALORIES_MALE,
    MIN_EXERCISE_SETS,
)
from core.capabilities.fitness.context import load_fitness_context
from core.capabilities.fitness.edit_ops import (
    BENCHMARK_WORKOUT_NOTE,
    EDIT_FAILED_NOTICE,
    apply_deterministic_edit,
    build_default_structured_workout,
    ensure_training_day_count,
    flatten_exercise_names,
    is_cacheable_workout,
    replace_exercise,
    resolve_expected_day_count,
)
from core.capabilities.fitness.macros import calculate_macros_data, compute_weekly_sets

# Re-exported under its private name: core/evaluation/owasp_prompt_robustness.py
# imports it directly to exercise the equipment-mismatch rule.
from core.capabilities.fitness.safety import _check_equipment_mismatch as _check_equipment_mismatch
from core.capabilities.fitness.safety import (
    collect_unsafe_markup_feedback,
    contains_unsafe_markup,
    humanize_safety_feedback,
    validate_workout_safety_data,
)
from core.capabilities.fitness.synthesis import build_workout_summary, synthesize_plan_data

__all__ = [
    "ACTIVITY_MULTIPLIERS",
    "BENCHMARK_WORKOUT_NOTE",
    "BODYWEIGHT_GYM_KEYWORDS",
    "DEFAULT_ACTIVITY_MULTIPLIER",
    "EDIT_FAILED_NOTICE",
    "HOME_GYM_KEYWORDS",
    "MAX_CALORIES",
    "MAX_EXERCISE_SETS",
    "MAX_PROTEIN_G_PER_KG",
    "MAX_TRAINING_DAYS",
    "MAX_WEEKLY_SETS",
    "MIN_CALORIES_FEMALE",
    "MIN_CALORIES_MALE",
    "MIN_EXERCISE_SETS",
    "apply_deterministic_edit",
    "build_default_structured_workout",
    "build_workout_summary",
    "calculate_macros_data",
    "collect_unsafe_markup_feedback",
    "compute_weekly_sets",
    "contains_unsafe_markup",
    "ensure_training_day_count",
    "flatten_exercise_names",
    "humanize_safety_feedback",
    "is_cacheable_workout",
    "load_fitness_context",
    "replace_exercise",
    "resolve_expected_day_count",
    "synthesize_plan_data",
    "validate_workout_safety_data",
    "write_fitness_artifacts",
]
