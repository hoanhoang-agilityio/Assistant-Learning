"""Fitness safety rules: macro bounds, equipment mismatches, unsafe markup,
and turning safety codes into human-readable feedback."""

import re
from typing import Any

from core.subgraphs.fitness.constants import (
    BODYWEIGHT_GYM_KEYWORDS,
    HOME_GYM_KEYWORDS,
    MAX_CALORIES,
    MAX_EXERCISE_SETS,
    MAX_PROTEIN_G_PER_KG,
    MAX_TRAINING_DAYS,
    MAX_WEEKLY_SETS,
    MIN_EXERCISE_SETS,
)
from core.subgraphs.fitness.macros import _minimum_calories, compute_weekly_sets
from core.subgraphs.fitness.schema import (
    SafetyResult,
    StructuredWorkout,
)


def _check_macro_safety(profile: dict[str, Any], macro_targets: dict[str, Any]) -> list[str]:
    feedback: list[str] = []
    calories = float(macro_targets["calories"])
    tdee = float(macro_targets["tdee"])
    weight_kg = float(profile["current_weight_kg"])
    protein_g = float(macro_targets["protein_g"])

    if calories < _minimum_calories(profile):
        feedback.append("calories_below_safe_minimum")
    if calories > MAX_CALORIES:
        feedback.append("calories_above_recommended_maximum")
    if tdee > 0 and calories < tdee * 0.75:
        feedback.append("aggressive_calorie_deficit")
    if protein_g / weight_kg > MAX_PROTEIN_G_PER_KG:
        feedback.append("protein_intake_too_high")
    return feedback


def _check_equipment_mismatch(
    exercise_name: str,
    equipment: str,
) -> str | None:
    name_lower = exercise_name.lower()
    if equipment == "bodyweight":
        for keyword in BODYWEIGHT_GYM_KEYWORDS:
            if keyword in name_lower:
                return f"equipment_mismatch:bodyweight:{exercise_name}"
    if equipment == "home":
        for keyword in HOME_GYM_KEYWORDS:
            if keyword in name_lower:
                return f"equipment_mismatch:home:{exercise_name}"
    return None


_UNSAFE_MARKUP_RE = re.compile(
    r"(?is)(<\s*script\b|</\s*script\s*>|javascript\s*:|onerror\s*=|onload\s*=|<\s*iframe\b)"
)


def contains_unsafe_markup(text: str | None) -> bool:
    """True when text embeds HTML/JS that must not appear in workout notes fields."""
    if not text:
        return False
    return _UNSAFE_MARKUP_RE.search(text) is not None


def collect_unsafe_markup_feedback(workout: StructuredWorkout) -> list[str]:
    """Return safety feedback codes for unsafe markup in plan or exercise notes."""
    feedback: list[str] = []
    for note in workout.notes:
        if contains_unsafe_markup(note):
            feedback.append("unsafe_markup_in_plan_notes")
            break
    for day in workout.days:
        for exercise in day.exercises:
            if contains_unsafe_markup(exercise.notes):
                feedback.append(f"unsafe_markup_in_notes:{exercise.name}")
    return feedback


def validate_workout_safety_data(
    profile: dict[str, Any],
    macro_targets: dict[str, Any] | None,
    training_constraints: dict[str, Any],
    structured_workout: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate macro targets and LLM workout output with deterministic rules.

    `macro_targets` is None when the profile has no weight/height/age on file (verify_plan
    without a completed profile) -- the macro-safety check is skipped rather than run
    against fabricated numbers, and that's recorded as a note, not a failure.
    """
    notes: list[str] = []
    if macro_targets is not None:
        feedback: list[str] = _check_macro_safety(profile, macro_targets)
    else:
        feedback = []
        notes.append(
            "macro_safety_skipped: no weight/height/age on file, so macro targets "
            "couldn't be checked"
        )

    if structured_workout is None:
        feedback.append("missing_structured_workout")
        return SafetyResult(passed=False, feedback=sorted(set(feedback)), notes=notes).model_dump()

    try:
        workout = StructuredWorkout.model_validate(structured_workout)
    except Exception:
        feedback.append("invalid_workout_schema")
        return SafetyResult(passed=False, feedback=sorted(set(feedback)), notes=notes).model_dump()

    expected_days = int(training_constraints["days_per_week"])
    actual_days = len(workout.days)
    equipment = str(training_constraints.get("equipment", "gym"))

    if actual_days != expected_days:
        feedback.append(f"training_day_count_mismatch:expected_{expected_days}_got_{actual_days}")
    if actual_days > MAX_TRAINING_DAYS:
        feedback.append("training_frequency_too_high")

    computed_sets = compute_weekly_sets(structured_workout)
    if workout.weekly_sets != computed_sets:
        feedback.append(
            f"weekly_sets_mismatch:declared_{workout.weekly_sets}_computed_{computed_sets}"
        )
    if workout.weekly_sets > MAX_WEEKLY_SETS or computed_sets > MAX_WEEKLY_SETS:
        feedback.append("weekly_training_volume_too_high")

    for day in workout.days:
        seen_in_day: dict[str, int] = {}
        if not day.exercises:
            feedback.append(f"empty_exercises:{day.name}")
        for exercise in day.exercises:
            if exercise.sets < MIN_EXERCISE_SETS or exercise.sets > MAX_EXERCISE_SETS:
                feedback.append(f"invalid_set_count:{exercise.name}:{exercise.sets}")
            normalized_name = exercise.name.strip().lower()
            seen_in_day[normalized_name] = seen_in_day.get(normalized_name, 0) + 1
            equipment_issue = _check_equipment_mismatch(exercise.name, equipment)
            if equipment_issue:
                feedback.append(equipment_issue)
        for name, count in seen_in_day.items():
            if count > 1:
                feedback.append(f"duplicate_exercise:{day.name}:{name}")

    feedback.extend(collect_unsafe_markup_feedback(workout))

    unique_feedback = sorted(set(feedback))
    return SafetyResult(
        passed=not unique_feedback, feedback=unique_feedback, notes=notes
    ).model_dump()


def humanize_safety_feedback(codes: list[str]) -> list[str]:
    """Translate `SafetyResult.feedback`'s internal codes into plain-English sentences.

    Used to keep raw codes (missing_structured_workout, training_day_count_mismatch:*, ...)
    out of anything user-facing -- either directly, or as clean input for an LLM asked to
    write a fuller natural-language explanation (see normalize.explain_verified_plan), so it
    never has to guess what a code means.
    """
    readable: list[str] = []
    for code in codes:
        prefix, _, rest = code.partition(":")
        if prefix == "training_day_count_mismatch":
            expected, _, got = rest.replace("expected_", "").replace("got_", "").partition("_")
            readable.append(
                f"The plan has {got} training day(s), but {expected} day(s) per week were expected."
            )
        elif prefix == "training_frequency_too_high":
            readable.append(
                f"Training frequency exceeds the safe maximum of {MAX_TRAINING_DAYS} days/week."
            )
        elif prefix == "weekly_sets_mismatch":
            readable.append("The declared weekly set total didn't match the actual sum of sets.")
        elif prefix == "weekly_training_volume_too_high":
            readable.append(
                f"Total weekly training volume is above the safe maximum of {MAX_WEEKLY_SETS} sets/week."
            )
        elif prefix == "empty_exercises":
            readable.append(f"'{rest}' has no exercises listed.")
        elif prefix == "invalid_set_count":
            exercise, _, sets = rest.rpartition(":")
            readable.append(
                f"'{exercise}' has an unusual set count ({sets}); expected between "
                f"{MIN_EXERCISE_SETS} and {MAX_EXERCISE_SETS}."
            )
        elif prefix == "equipment_mismatch":
            setting, _, exercise = rest.partition(":")
            readable.append(f"'{exercise}' needs equipment that may not fit a {setting} setup.")
        elif prefix == "duplicate_exercise":
            day, _, name = rest.partition(":")
            readable.append(f"'{name}' appears more than once on {day}.")
        elif prefix == "calories_below_safe_minimum":
            readable.append("The calorie target is below the safe minimum.")
        elif prefix == "calories_above_recommended_maximum":
            readable.append("The calorie target is above the recommended maximum.")
        elif prefix == "aggressive_calorie_deficit":
            readable.append("The calorie target is an aggressive deficit relative to maintenance.")
        elif prefix == "protein_intake_too_high":
            readable.append("The protein target is unusually high relative to body weight.")
        elif prefix == "invalid_workout_schema":
            readable.append("The submitted plan didn't match the expected workout format.")
        elif prefix == "missing_structured_workout":
            readable.append("No structured workout could be found in the submitted text.")
        elif prefix == "unsafe_markup_in_plan_notes":
            readable.append(
                "Plan notes contain HTML or script markup; notes must be plain coaching text."
            )
        elif prefix == "unsafe_markup_in_notes":
            readable.append(
                f"Notes for '{rest}' contain HTML or script markup; notes must be plain text."
            )
        else:
            readable.append(code.replace("_", " ").replace(":", ": "))
    return readable
