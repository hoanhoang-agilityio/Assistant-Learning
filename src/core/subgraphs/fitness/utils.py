import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.planning.utils import has_execution_plan, load_execution_plan
from core.profile.goal_spec import GoalSpec, rate_to_calorie_adjustment
from core.profile.normalize import resolve_activity_level
from core.profile.store import load_run_profile, split_constraints
from core.subgraphs.fitness.schema import (
    EditOperation,
    SafetyResult,
    StructuredWorkout,
    WorkoutDay,
    WorkoutExercise,
)
from core.vfs import VFS

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "gym_1x_week": 1.375,
    "gym_2x_week": 1.375,
    "gym_3x_week": 1.55,
    "gym_4x_week": 1.55,
    "gym_5x_week": 1.725,
    "gym_6x_week": 1.725,
}
DEFAULT_ACTIVITY_MULTIPLIER = 1.375
MIN_CALORIES_FEMALE = 1200
MIN_CALORIES_MALE = 1500
MAX_CALORIES = 4500
MAX_PROTEIN_G_PER_KG = 3.0
MAX_TRAINING_DAYS = 6
MAX_WEEKLY_SETS = 120
MIN_EXERCISE_SETS = 1
MAX_EXERCISE_SETS = 10

BODYWEIGHT_GYM_KEYWORDS = (
    "barbell",
    "smith machine",
    "cable",
    "leg press",
    "lat pulldown",
    "machine",
    "rack",
)

HOME_GYM_KEYWORDS = (
    "cable machine",
    "leg press",
    "smith machine",
    "lat pulldown",
    "hack squat",
)


def load_fitness_context(workspace_path: str) -> dict[str, Any]:
    """Hydrate Fitness's VFS-backed context: profile+constraints, execution plan, research
    findings, and prior verification feedback. `plan/profile.json` stores profile and
    constraint fields together as one flat dict, so `constraints` here is derived via
    `split_constraints` rather than read from a separate artifact.
    """
    vfs = VFS.for_run(Path(workspace_path))
    profile = load_run_profile(workspace_path)
    evidence_summary: str | None = None
    structured_findings: dict[str, Any] | None = None
    verification_feedback: str | None = None
    execution_plan: dict[str, Any] | None = None

    if has_execution_plan(workspace_path):
        execution_plan = load_execution_plan(workspace_path).model_dump()

    if vfs.exists("research/findings.json"):
        findings = json.loads(vfs.read("research/findings.json"))
        structured = findings.get("structured_findings")
        if isinstance(structured, dict) and structured.get("consensus"):
            structured_findings = structured
            evidence_summary = _format_structured_evidence_summary(structured)
        else:
            evidence_summary = findings.get("evidence_summary")

    if vfs.exists("verify/verification_v1.json"):
        verification = json.loads(vfs.read("verify/verification_v1.json"))
        verification_feedback = verification.get("feedback")

    return {
        "profile": profile,
        "constraints": split_constraints(profile),
        "execution_plan": execution_plan,
        "structured_findings": structured_findings,
        "evidence_summary": evidence_summary,
        "verification_feedback": verification_feedback,
    }


def load_prior_safety_feedback(workspace_path: str) -> list[str]:
    """Load prior safety feedback persisted from an earlier Fitness run."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("fitness/safety_flags.json"):
        return []
    raw = json.loads(vfs.read("fitness/safety_flags.json"))
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _format_structured_evidence_summary(structured: dict[str, Any]) -> str:
    lines = [str(structured.get("consensus", ""))]
    key_findings = structured.get("key_findings") or []
    if key_findings:
        lines.append("")
        lines.append("Key findings:")
        for finding in key_findings:
            lines.append(f"- {finding}")
    return "\n".join(line for line in lines if line)


def _calculate_bmr(profile: dict[str, Any]) -> float:
    weight_kg = float(profile["current_weight_kg"])
    height_cm = float(profile["height_cm"])
    age = int(profile["age"])
    sex = str(profile.get("sex", "male")).lower()
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if sex == "female":
        return base - 161
    return base + 5


def _activity_multiplier(activity_level: str) -> float:
    return ACTIVITY_MULTIPLIERS.get(activity_level, DEFAULT_ACTIVITY_MULTIPLIER)


def _minimum_calories(profile: dict[str, Any]) -> float:
    sex = str(profile.get("sex", "male")).lower()
    if sex == "female":
        return MIN_CALORIES_FEMALE
    return MIN_CALORIES_MALE


_REQUIRED_BIOMETRIC_FIELDS = ("current_weight_kg", "height_cm", "age")


def _has_required_biometrics(profile: dict[str, Any]) -> bool:
    return all(profile.get(field) is not None for field in _REQUIRED_BIOMETRIC_FIELDS)


def calculate_macros_data(
    profile: dict[str, Any],
    constraints: dict[str, Any],
    goal_spec: GoalSpec,
) -> dict[str, Any]:
    """`goal_spec` must be derived by the caller from this same `profile` -- see the
    single-derivation threading rule in core/profile/goal_spec.py.

    `macro_targets` is None when `profile` is missing weight/height/age (e.g. verify_plan,
    which has requires_profile=False) -- personalized calorie/macro math is meaningless
    without them, so this degrades gracefully instead of raising, matching how `goal`/
    `activity_level` above already default rather than requiring a complete profile.
    `training_constraints` never needs biometrics, so it's always computed.
    """
    goal = str(profile.get("goal", "general_fitness"))
    activity_level = resolve_activity_level(profile.get("days_per_week"))
    training_constraints = {
        "days_per_week": _parse_training_days(activity_level, constraints, profile),
        "session_duration_minutes": int(constraints.get("session_duration_minutes", 60)),
        "equipment": constraints.get("equipment", "gym"),
        "goal": goal,
    }
    if not _has_required_biometrics(profile):
        return {"macro_targets": None, "training_constraints": training_constraints}

    weight_kg = float(profile["current_weight_kg"])
    weekly_rate_kg = goal_spec.weekly_rate_kg

    bmr = _calculate_bmr(profile)
    tdee = bmr * _activity_multiplier(activity_level)
    calories = rate_to_calorie_adjustment(goal, tdee, weekly_rate_kg)
    calories = max(calories, _minimum_calories(profile))
    calories = min(calories, MAX_CALORIES)

    protein_grams_per_kg = 2.2 if goal in {"muscle_gain", "strength", "recomposition"} else 1.8
    if constraints.get("high_protein"):
        protein_grams_per_kg = 2.4
    if goal == "recomposition":
        protein_grams_per_kg = max(protein_grams_per_kg, 2.2)
    protein_g = round(weight_kg * protein_grams_per_kg)

    fat_calories = calories * 0.25
    fat_g = round(fat_calories / 9)
    carb_g = round(max((calories - (protein_g * 4) - (fat_g * 9)) / 4, 0))

    macro_targets = {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "calories": round(calories),
        "protein_g": protein_g,
        "carbs_g": carb_g,
        "fat_g": fat_g,
        "goal": goal,
        "activity_level": activity_level,
    }
    return {
        "macro_targets": macro_targets,
        "training_constraints": training_constraints,
    }


def _parse_training_days(
    activity_level: str,
    constraints: dict[str, Any],
    profile: dict[str, Any],
) -> int:
    if profile.get("days_per_week") is not None:
        return int(profile["days_per_week"])
    if "days_per_week" in constraints:
        return int(constraints["days_per_week"])
    match = re.search(r"gym_(\d+)x_week", activity_level)
    if match:
        return int(match.group(1))
    return 3


def compute_weekly_sets(structured_workout: dict[str, Any]) -> int:
    """Sum exercise sets across all days in a structured workout."""
    return sum(
        int(exercise["sets"])
        for day in structured_workout.get("days", [])
        for exercise in day.get("exercises", [])
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
        else:
            readable.append(code.replace("_", " ").replace(":", ": "))
    return readable


EDIT_FAILED_NOTICE = (
    "> **Note:** I couldn't apply your requested change precisely, so your plan is "
    "unchanged from before. Try naming the specific day or exercise you mean and "
    "I'll try again.\n\n"
)


def synthesize_plan_data(
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any] | None,
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_result: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
    edit_failed: bool = False,
) -> dict[str, Any]:
    if structured_workout is None:
        return {"draft_plan": "# Fitness Plan Draft\n\nWorkout plan unavailable.\n"}

    days_markdown: list[str] = []
    for index, day in enumerate(structured_workout.get("days", []), start=1):
        exercise_lines = "\n".join(
            f"  - {exercise['name']}: {exercise['sets']} x {exercise['reps']}"
            for exercise in day.get("exercises", [])
        )
        days_markdown.append(
            f"### Day {index} — {day['name']}\nFocus: {day['focus']}\n{exercise_lines}"
        )

    progression = structured_workout.get("progression")
    progression_section = ""
    if progression:
        progression_section = f"\n## Progression\n\n{progression}\n"

    substitutions = structured_workout.get("substitutions") or []
    substitutions_section = ""
    if substitutions:
        sub_lines = "\n".join(f"- {item}" for item in substitutions)
        substitutions_section = f"\n## Substitutions\n\n{sub_lines}\n"

    notes = structured_workout.get("notes") or []
    notes_section = ""
    if notes:
        note_lines = "\n".join(f"- {note}" for note in notes)
        notes_section = f"\n## Notes\n\n{note_lines}\n"

    evidence_applied = structured_workout.get("evidence_applied") or []
    evidence_applied_section = ""
    if evidence_applied:
        applied_lines = "\n".join(f"- {item}" for item in evidence_applied)
        evidence_applied_section = f"\n## Evidence Applied\n\n{applied_lines}\n"

    feedback_section = ""
    if verification_feedback:
        feedback_section = f"\n## Verification Feedback Applied\n\n{verification_feedback}\n"

    evidence_section = ""
    if evidence_summary:
        evidence_section = f"\n## Evidence Summary\n\n{evidence_summary}\n"

    safety_section = ""
    safety_feedback = safety_result.get("feedback") or []
    if safety_feedback:
        safety_lines = "\n".join(f"- {item}" for item in safety_feedback)
        safety_section = f"\n## Safety Warnings\n\n{safety_lines}\n"

    blueprint_section = ""
    if plan_blueprint:
        horizon = plan_blueprint.get("horizon_weeks")
        weekly_rate = plan_blueprint.get("weekly_rate_kg")
        blueprint_lines = ["## Program Blueprint", ""]
        if horizon:
            blueprint_lines.append(f"- Horizon: {horizon} weeks")
        if weekly_rate is not None:
            blueprint_lines.append(f"- Target weekly rate: {weekly_rate} kg")
        blueprint_lines.append(f"- Archetype: {plan_blueprint.get('goal_archetype', 'n/a')}")
        phases = plan_blueprint.get("phases") or []
        if phases:
            blueprint_lines.append("- Phases:")
            for phase in phases:
                blueprint_lines.append(
                    f"  - Weeks {phase['week_start']}-{phase['week_end']}: "
                    f"{phase['training_emphasis']} (volume x{phase['volume_modifier']})"
                )
        progression_notes = plan_blueprint.get("progression_notes") or []
        for note in progression_notes:
            blueprint_lines.append(f"- {note}")
        blueprint_section = "\n".join(blueprint_lines) + "\n\n"

    draft_plan = (
        "# Fitness Plan Draft\n\n"
        f"{blueprint_section}"
        "## Macro Targets\n\n"
        f"- Calories: {macro_targets['calories']} kcal\n"
        f"- Protein: {macro_targets['protein_g']} g\n"
        f"- Carbs: {macro_targets['carbs_g']} g\n"
        f"- Fat: {macro_targets['fat_g']} g\n\n"
        "## Training Plan\n\n"
        f"Split: {structured_workout['split']} ({structured_workout['goal']})\n\n"
        f"{chr(10).join(days_markdown)}"
        f"{progression_section}"
        f"{substitutions_section}"
        f"{notes_section}"
        f"{evidence_applied_section}"
        f"{evidence_section}"
        f"{feedback_section}"
        f"{safety_section}"
    )
    if edit_failed:
        draft_plan = draft_plan.replace(
            "# Fitness Plan Draft\n\n", "# Fitness Plan Draft\n\n" + EDIT_FAILED_NOTICE, 1
        )
    return {"draft_plan": draft_plan}


def build_workout_summary(structured_workout: dict[str, Any]) -> dict[str, Any]:
    """Derive a compact workout summary for downstream verification."""
    return {
        "split": structured_workout["split"],
        "goal": structured_workout["goal"],
        "weekly_sets": structured_workout["weekly_sets"],
        "sessions": len(structured_workout.get("days", [])),
    }


def write_fitness_artifacts(
    workspace_path: str,
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any],
    draft_plan: str,
    safety_result: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
    template_fingerprint: str | None = None,
    workout_source: str | None = None,
    normalization_findings: list[str] | None = None,
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    workout_summary = build_workout_summary(structured_workout)
    calculations = {
        "macro_targets": macro_targets,
        "workout_summary": workout_summary,
        "training_plan_summary": workout_summary,
    }
    if plan_blueprint is not None:
        calculations["plan_blueprint"] = plan_blueprint
    vfs.write("fitness/workout.json", json.dumps(structured_workout, indent=2))
    vfs.write("fitness/calculations.json", json.dumps(calculations, indent=2))
    if plan_blueprint is not None:
        vfs.write("fitness/blueprint.json", json.dumps(plan_blueprint, indent=2))
    if template_fingerprint is not None:
        vfs.write(
            "fitness/template_fingerprint.json",
            json.dumps(
                {
                    "fingerprint": template_fingerprint,
                    "workout_source": workout_source,
                },
                indent=2,
            ),
        )
    safety_feedback = safety_result.get("feedback") or []
    vfs.write("fitness/safety_flags.json", json.dumps(safety_feedback, indent=2))
    # The feedback strings above are only the 4-flag allowlist Verification's
    # safety_check_data historically re-derived from -- the actual pass/fail
    # boolean validate_workout_safety_data computed (covering every flag it
    # can emit, not just that subset) was never persisted anywhere, so an
    # equipment mismatch, duplicate exercise, or invalid set count could pass
    # Verification's safety gate silently. Persist it directly.
    vfs.write("fitness/safety_passed.json", json.dumps(safety_result["passed"]))
    vfs.write(
        "fitness/normalization_findings.json",
        json.dumps(normalization_findings or [], indent=2),
    )
    vfs.write("fitness/final_plan.md", draft_plan)


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


def _day_signature(day: dict[str, Any]) -> tuple[Any, ...]:
    """Comparable snapshot of a workout day for preservation checks: focus +
    ordered exercise names only. Deliberately excludes sets/reps/notes -- this
    is a minimal regression check, not a full diff.
    """
    exercise_names = tuple(str(exercise.get("name", "")) for exercise in day.get("exercises", []))
    return (str(day.get("focus", "")), exercise_names)


def _add_day_unrelated_days_changed(
    previous_workout: dict[str, Any], new_workout: dict[str, Any]
) -> bool:
    """For ADD_DAY: every pre-existing day (assumed to stay in place, new day appended
    last -- no stable day IDs to pin its position otherwise) must be unchanged. Not a
    general diff: a plain positional prefix comparison, only ever called once the day
    count itself has already been confirmed to be prev+1.
    """
    prev_sig = [_day_signature(day) for day in previous_workout.get("days", [])]
    new_sig = [_day_signature(day) for day in new_workout.get("days", [])]
    return prev_sig != new_sig[: len(prev_sig)]


def _remove_day_unrelated_days_changed(
    previous_workout: dict[str, Any], new_workout: dict[str, Any]
) -> bool:
    """For REMOVE_DAY: the remaining days must equal the previous days with exactly
    one entry removed, in the same order. Checked by brute force over the (<=6) day
    positions rather than a general diff, since day counts are tiny; only ever called
    once the day count itself has already been confirmed to be prev-1.
    """
    prev_sig = [_day_signature(day) for day in previous_workout.get("days", [])]
    new_sig = [_day_signature(day) for day in new_workout.get("days", [])]
    return not any(prev_sig[:i] + prev_sig[i + 1 :] == new_sig for i in range(len(prev_sig)))


def validate_edit_result(
    operation: EditOperation,
    previous_workout: dict[str, Any],
    new_workout: dict[str, Any],
) -> list[str]:
    """Lightweight, intentionally non-exhaustive checks that an edit did what it claimed.

    Not a diff engine: two day-count comparisons, one positional-prefix
    preservation check each for ADD_DAY/REMOVE_DAY, and two name-membership
    checks, reusing the same feedback-string convention as
    validate_workout_safety_data so callers can merge results into one list.
    """
    issues: list[str] = []
    prev_days = len(previous_workout.get("days", []))
    new_days = len(new_workout.get("days", []))
    if operation.operation == "ADD_DAY":
        if new_days != prev_days + 1:
            issues.append("edit_validation_failed:day_count_did_not_increase")
        elif _add_day_unrelated_days_changed(previous_workout, new_workout):
            issues.append("edit_validation_failed:unrelated_day_changed")
    elif operation.operation == "REMOVE_DAY":
        if new_days != prev_days - 1:
            issues.append("edit_validation_failed:day_count_did_not_decrease")
        elif _remove_day_unrelated_days_changed(previous_workout, new_workout):
            issues.append("edit_validation_failed:unrelated_day_changed")
    elif operation.operation == "REPLACE_EXERCISE":
        names = {
            str(exercise.get("name", "")).strip().lower()
            for day in new_workout.get("days", [])
            for exercise in day.get("exercises", [])
        }
        replacement = (operation.replacement_exercise or "").strip().lower()
        target = (operation.target_exercise or "").strip().lower()
        if replacement and replacement not in names:
            issues.append("edit_validation_failed:replacement_missing")
        if target and target in names:
            issues.append("edit_validation_failed:target_still_present")
    return issues


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
        evidence_applied=["Applied general hypertrophy volume guidance."],
    )
