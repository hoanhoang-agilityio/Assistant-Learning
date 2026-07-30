"""Deterministic plan edits: default workout templates, day-count fixes and
exercise replacement."""

from copy import deepcopy
from typing import Any

from core.subgraphs.fitness.schema import (
    EditOperation,
    StructuredWorkout,
    WorkoutDay,
    WorkoutExercise,
)

EDIT_FAILED_NOTICE = (
    "> **Note:** I couldn't apply your requested change precisely, so your plan is "
    "unchanged from before. Try naming the specific day or exercise you mean and "
    "I'll try again.\n\n"
)


BENCHMARK_WORKOUT_NOTE = "Default deterministic workout for tests and benchmarks."


def is_cacheable_workout(workout: dict[str, Any]) -> bool:
    """Return False for benchmark/fallback workouts that must not enter the registry."""
    notes = workout.get("notes") or []
    return not any(BENCHMARK_WORKOUT_NOTE in str(note) for note in notes)


_DEFAULT_PUSH_EXERCISES = (
    WorkoutExercise(name="Bench Press", sets=3, reps="6-10"),
    WorkoutExercise(name="Overhead Press", sets=3, reps="8-10"),
    WorkoutExercise(name="Triceps Pushdown", sets=3, reps="10-12"),
)
_DEFAULT_PULL_EXERCISES = (
    WorkoutExercise(name="Barbell Row", sets=3, reps="6-10"),
    WorkoutExercise(name="Lat Pulldown", sets=3, reps="8-12"),
    WorkoutExercise(name="Face Pull", sets=3, reps="12-15"),
)
_DEFAULT_LEGS_EXERCISES = (
    WorkoutExercise(name="Goblet Squat", sets=3, reps="8-10"),
    WorkoutExercise(name="Romanian Deadlift", sets=3, reps="8-12"),
    WorkoutExercise(name="Walking Lunge", sets=3, reps="10-12"),
)
_DEFAULT_FULL_BODY_EXERCISES = (
    WorkoutExercise(name="Goblet Squat", sets=3, reps="8-10"),
    WorkoutExercise(name="Push-up", sets=3, reps="8-12"),
    WorkoutExercise(name="Romanian Deadlift", sets=3, reps="8-12"),
    WorkoutExercise(name="Row", sets=3, reps="10-12"),
)
_DEFAULT_DAY_ROTATIONS: tuple[tuple[str, tuple[WorkoutExercise, ...]], ...] = (
    ("push", _DEFAULT_PUSH_EXERCISES),
    ("pull", _DEFAULT_PULL_EXERCISES),
    ("legs", _DEFAULT_LEGS_EXERCISES),
)


def _default_day_templates(days_per_week: int) -> list[tuple[str, tuple[WorkoutExercise, ...]]]:
    if days_per_week <= 1:
        return [("full body", _DEFAULT_FULL_BODY_EXERCISES)]
    return [
        _DEFAULT_DAY_ROTATIONS[index % len(_DEFAULT_DAY_ROTATIONS)]
        for index in range(days_per_week)
    ]


def resolve_expected_day_count(
    operation: EditOperation | None,
    previous_workout: dict[str, Any] | None,
    training_constraints: dict[str, Any],
    *,
    days_per_week_explicit: bool = False,
) -> int:
    """Resolve the day count a workout should have this run.

    When the current revision explicitly named a training-frequency target
    (days_per_week_explicit), that target -- training_constraints["days_per_week"],
    sourced from the freshly revised profile -- is authoritative, regardless of edit
    operation or previous day count. profile.days_per_week is the single source of
    truth for user-requested frequency; EditOperation only decides edit *strategy*.

    Otherwise, during an edit (operation + previous_workout both present), the
    expected count is derived from the plan being edited -- ADD_DAY/REMOVE_DAY adjust
    it by one, anything else keeps it the same -- never from the static,
    profile-derived training_constraints["days_per_week"], which can be stale
    relative to a plan already edited in an earlier turn (e.g. a prior
    successful ADD_DAY took it from 4 to 5 days, but training_constraints still
    says 4). This is the single source of truth for that value, used
    identically by generation (ensure_training_day_count) and validation
    (validate_workout_safety_data) so they can never disagree.

    Fresh generation (no operation/previous_workout) is unchanged: falls back
    to training_constraints["days_per_week"] exactly as before.
    """
    if days_per_week_explicit:
        return int(training_constraints["days_per_week"])
    if operation is not None and previous_workout is not None:
        prev_day_count = len(previous_workout.get("days", []))
        if operation.operation == "ADD_DAY":
            return prev_day_count + 1
        if operation.operation == "REMOVE_DAY":
            return prev_day_count - 1
        return prev_day_count
    return int(training_constraints["days_per_week"])


def ensure_training_day_count(
    workout: StructuredWorkout,
    training_constraints: dict[str, Any],
    profile: dict[str, Any],
) -> StructuredWorkout:
    """Normalize LLM workouts so day count always matches training_constraints."""
    expected_days = int(training_constraints["days_per_week"])
    actual_days = len(workout.days)
    if actual_days == expected_days:
        return workout
    if actual_days > expected_days:
        trimmed_days = workout.days[:expected_days]
        weekly_sets = sum(exercise.sets for day in trimmed_days for exercise in day.exercises)
        return workout.model_copy(update={"days": trimmed_days, "weekly_sets": weekly_sets})
    fallback = build_default_structured_workout(
        profile,
        {
            "days_per_week": expected_days,
            "equipment": training_constraints.get("equipment", "gym"),
        },
    )
    return fallback.model_copy(
        update={
            "goal": workout.goal or fallback.goal,
            "evidence_applied": workout.evidence_applied or fallback.evidence_applied,
            "notes": list(dict.fromkeys([*workout.notes, *fallback.notes])),
        }
    )


def replace_exercise(
    workout: dict[str, Any],
    target: str | None,
    replacement: str | None,
) -> dict[str, Any] | None:
    """Deterministically rename one exercise across all days.

    Returns None (signalling "fall back to edit-mode generation") unless the
    target name matches exactly one exercise in the workout -- ambiguous or
    missing matches are not guessed at.
    """
    if not target or not replacement:
        return None
    target_lower = target.strip().lower()
    updated = deepcopy(workout)
    matches = [
        exercise
        for day in updated.get("days", [])
        for exercise in day.get("exercises", [])
        if str(exercise.get("name", "")).strip().lower() == target_lower
    ]
    if len(matches) != 1:
        return None
    matches[0]["name"] = replacement
    return updated


def apply_deterministic_edit(
    operation: EditOperation,
    previous_workout: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply an edit operation without an LLM call, or None to fall back to edit mode.

    UPDATE_MACROS never touches the workout -- the macro recompute happens
    entirely outside workout generation (calculate_macros_data), so reusing
    the previous workout unchanged is the correct result, not a shortcut.
    """
    if operation.operation == "UPDATE_MACROS":
        return previous_workout
    if operation.operation == "REPLACE_EXERCISE":
        return replace_exercise(
            previous_workout,
            operation.target_exercise,
            operation.replacement_exercise,
        )
    return None


def flatten_exercise_names(workout: dict[str, Any]) -> list[str]:
    """Flat list of exercise names across all days, for edit-classifier grounding."""
    return [
        str(exercise.get("name", ""))
        for day in workout.get("days", [])
        for exercise in day.get("exercises", [])
    ]


def build_default_structured_workout(
    profile: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> StructuredWorkout:
    """Build a deterministic fallback structured workout for tests and benchmarks."""
    resolved_profile = profile or {}
    resolved_constraints = constraints or {}
    goal = str(resolved_profile.get("goal", "general_fitness"))
    days_per_week = int(
        resolved_constraints.get("days_per_week") or resolved_profile.get("days_per_week") or 3
    )
    day_templates = _default_day_templates(days_per_week)
    days = [
        WorkoutDay(
            name=f"Day {index + 1}",
            focus=focus,
            exercises=[exercise.model_copy() for exercise in exercises],
        )
        for index, (focus, exercises) in enumerate(day_templates)
    ]
    weekly_sets = sum(exercise.sets for day in days for exercise in day.exercises)
    split_label = "full body" if days_per_week <= 1 else "push/pull/legs rotation"
    return StructuredWorkout(
        split=f"{days_per_week}-day {split_label}",
        goal=goal,
        days=days,
        weekly_sets=weekly_sets,
        progression="Add 2.5-5 kg or 1-2 reps when all sets hit the top of the rep range.",
        substitutions=["Swap barbell movements for dumbbells when equipment is limited."],
        notes=[BENCHMARK_WORKOUT_NOTE],
        evidence_applied=[],
    )
