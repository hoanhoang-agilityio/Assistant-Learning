import json
import re
from pathlib import Path
from typing import Any

from core.subgraphs.fitness.schema import (
    SafetyResult,
    StructuredWorkout,
    WorkoutDay,
    WorkoutExercise,
)
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.planning.utils import has_execution_plan, load_execution_plan
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
    vfs = VFS.for_run(Path(workspace_path))
    profile: dict[str, Any] = {}
    evidence_summary: str | None = None
    structured_findings: dict[str, Any] | None = None
    verification_feedback: str | None = None
    execution_plan: dict[str, Any] = {}

    if vfs.exists("plan/profile.json"):
        profile = json.loads(vfs.read("plan/profile.json"))

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
        "execution_plan": execution_plan,
        "structured_findings": structured_findings,
        "evidence_summary": evidence_summary,
        "verification_feedback": verification_feedback,
    }


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


def _goal_calorie_adjustment(goal: str, tdee: float) -> float:
    if goal == "fat_loss":
        return tdee - 500
    if goal == "muscle_gain":
        return tdee + 300
    if goal == "strength":
        return tdee + 200
    return tdee


def _minimum_calories(profile: dict[str, Any]) -> float:
    sex = str(profile.get("sex", "male")).lower()
    if sex == "female":
        return MIN_CALORIES_FEMALE
    return MIN_CALORIES_MALE


def calculate_macros_data(profile: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    goal = str(profile.get("goal", "general_fitness"))
    activity_level = str(profile.get("activity_level", "gym_3x_week"))
    weight_kg = float(profile["current_weight_kg"])

    bmr = _calculate_bmr(profile)
    tdee = bmr * _activity_multiplier(activity_level)
    calories = _goal_calorie_adjustment(goal, tdee)
    calories = max(calories, _minimum_calories(profile))
    calories = min(calories, MAX_CALORIES)

    protein_grams_per_kg = 2.2 if goal in {"muscle_gain", "strength"} else 1.8
    if constraints.get("high_protein"):
        protein_grams_per_kg = 2.4
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
    training_constraints = {
        "days_per_week": _parse_training_days(activity_level, constraints, profile),
        "session_duration_minutes": int(constraints.get("session_duration_minutes", 60)),
        "equipment": constraints.get("equipment", "gym"),
        "goal": goal,
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
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    structured_workout: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate macro targets and LLM workout output with deterministic rules."""
    feedback: list[str] = _check_macro_safety(profile, macro_targets)

    if structured_workout is None:
        feedback.append("missing_structured_workout")
        return SafetyResult(passed=False, feedback=sorted(set(feedback))).model_dump()

    try:
        workout = StructuredWorkout.model_validate(structured_workout)
    except Exception:
        feedback.append("invalid_workout_schema")
        return SafetyResult(passed=False, feedback=sorted(set(feedback))).model_dump()

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
    return SafetyResult(passed=not unique_feedback, feedback=unique_feedback).model_dump()


def synthesize_plan_data(
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any] | None,
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_result: dict[str, Any],
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

    draft_plan = (
        "# Fitness Plan Draft\n\n"
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
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    workout_summary = build_workout_summary(structured_workout)
    calculations = {
        "macro_targets": macro_targets,
        "workout_summary": workout_summary,
        "training_plan_summary": workout_summary,
    }
    vfs.write("fitness/workout.json", json.dumps(structured_workout, indent=2))
    vfs.write("fitness/calculations.json", json.dumps(calculations, indent=2))
    safety_feedback = safety_result.get("feedback") or []
    vfs.write("fitness/safety_flags.json", json.dumps(safety_feedback, indent=2))
    vfs.write("fitness/final_plan.md", draft_plan)


def default_execution_plan_for_fitness(execution_plan: dict[str, Any]) -> ExecutionPlan:
    """Return a valid execution plan, using a minimal fallback when VFS plan is absent."""
    if execution_plan:
        return ExecutionPlan.model_validate(execution_plan)
    from core.subgraphs.planning.utils import build_default_execution_plan

    return build_default_execution_plan()


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
    exercise_models = [
        WorkoutExercise(name="Goblet Squat", sets=3, reps="8-10"),
        WorkoutExercise(name="Push-up", sets=3, reps="8-12"),
        WorkoutExercise(name="Romanian Deadlift", sets=3, reps="8-12"),
        WorkoutExercise(name="Row", sets=3, reps="10-12"),
    ]
    weekly_sets = days_per_week * sum(exercise.sets for exercise in exercise_models)
    days = [
        WorkoutDay(
            name=f"Day {index + 1}",
            focus="full body",
            exercises=exercise_models,
        )
        for index in range(days_per_week)
    ]
    return StructuredWorkout(
        split=f"{days_per_week}-day",
        goal=goal,
        days=days,
        weekly_sets=weekly_sets,
        progression="Add 2.5-5 kg or 1-2 reps when all sets hit the top of the rep range.",
        substitutions=["Swap barbell movements for dumbbells when equipment is limited."],
        notes=["Default deterministic workout for tests and benchmarks."],
        evidence_applied=["Applied general hypertrophy volume guidance."],
    )
