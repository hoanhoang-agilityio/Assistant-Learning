import json
import re
from pathlib import Path
from typing import Any

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


def load_fitness_context(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    profile: dict[str, Any] = {}
    evidence_summary: str | None = None
    verification_feedback: str | None = None

    if vfs.exists("plan/profile.json"):
        profile = json.loads(vfs.read("plan/profile.json"))

    if vfs.exists("research/findings.json"):
        findings = json.loads(vfs.read("research/findings.json"))
        evidence_summary = findings.get("evidence_summary")

    if vfs.exists("verify/verification_v1.json"):
        verification = json.loads(vfs.read("verify/verification_v1.json"))
        verification_feedback = verification.get("feedback")

    return {
        "profile": profile,
        "evidence_summary": evidence_summary,
        "verification_feedback": verification_feedback,
    }


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
        "days_per_week": _parse_training_days(activity_level, constraints),
        "session_duration_minutes": int(constraints.get("session_duration_minutes", 60)),
        "equipment": constraints.get("equipment", "gym"),
        "goal": goal,
    }
    return {
        "macro_targets": macro_targets,
        "training_constraints": training_constraints,
    }


def _parse_training_days(activity_level: str, constraints: dict[str, Any]) -> int:
    if "days_per_week" in constraints:
        return int(constraints["days_per_week"])
    match = re.search(r"gym_(\d+)x_week", activity_level)
    if match:
        return int(match.group(1))
    return 3


def _session_templates(days_per_week: int, goal: str) -> list[dict[str, Any]]:
    if days_per_week <= 3:
        focus = "hypertrophy" if goal in {"muscle_gain", "strength"} else "fat_loss conditioning"
        return [
            {
                "day": index + 1,
                "name": f"Full Body {index + 1}",
                "focus": focus,
                "exercises": [
                    {"name": "Squat", "sets": 3, "reps": "6-10"},
                    {"name": "Bench Press", "sets": 3, "reps": "6-10"},
                    {"name": "Romanian Deadlift", "sets": 3, "reps": "8-12"},
                    {"name": "Lat Pulldown", "sets": 3, "reps": "10-12"},
                ],
            }
            for index in range(days_per_week)
        ]

    if days_per_week == 4:
        blocks = [
            ("Upper A", "upper body strength"),
            ("Lower A", "lower body strength"),
            ("Upper B", "upper body hypertrophy"),
            ("Lower B", "lower body hypertrophy"),
        ]
    else:
        blocks = [
            ("Push", "pressing muscles"),
            ("Pull", "back and biceps"),
            ("Legs", "quads, hamstrings, glutes"),
            ("Upper", "upper body volume"),
            ("Lower", "lower body volume"),
        ]

    sessions: list[dict[str, Any]] = []
    for index in range(days_per_week):
        name, focus = blocks[index % len(blocks)]
        sessions.append(
            {
                "day": index + 1,
                "name": name,
                "focus": focus,
                "exercises": [
                    {"name": "Compound Lift", "sets": 4, "reps": "5-8"},
                    {"name": "Accessory 1", "sets": 3, "reps": "8-12"},
                    {"name": "Accessory 2", "sets": 3, "reps": "10-15"},
                ],
            }
        )
    return sessions


def build_training_plan_data(
    profile: dict[str, Any],
    macro_targets: dict[str, Any],
    training_constraints: dict[str, Any],
    evidence_summary: str | None,
) -> dict[str, Any]:
    del profile
    days_per_week = int(training_constraints["days_per_week"])
    goal = str(training_constraints["goal"])
    sessions = _session_templates(days_per_week, goal)
    training_plan = {
        "split": f"{days_per_week}-day",
        "goal": goal,
        "sessions": sessions,
        "weekly_sets": sum(
            exercise["sets"] for session in sessions for exercise in session["exercises"]
        ),
        "evidence_summary": evidence_summary,
    }
    return {"training_plan": training_plan}


def detect_safety_flags_data(
    profile: dict[str, Any],
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
) -> dict[str, Any]:
    flags: list[str] = []
    calories = float(macro_targets["calories"])
    tdee = float(macro_targets["tdee"])
    weight_kg = float(profile["current_weight_kg"])
    protein_g = float(macro_targets["protein_g"])
    days_per_week = len(training_plan.get("sessions", []))
    weekly_sets = int(training_plan.get("weekly_sets", 0))

    if calories < _minimum_calories(profile):
        flags.append("calories_below_safe_minimum")
    if calories > MAX_CALORIES:
        flags.append("calories_above_recommended_maximum")
    if tdee > 0 and calories < tdee * 0.75:
        flags.append("aggressive_calorie_deficit")
    if protein_g / weight_kg > MAX_PROTEIN_G_PER_KG:
        flags.append("protein_intake_too_high")
    if days_per_week > MAX_TRAINING_DAYS:
        flags.append("training_frequency_too_high")
    if weekly_sets > MAX_WEEKLY_SETS:
        flags.append("weekly_training_volume_too_high")

    return {"safety_flags": sorted(set(flags))}


def synthesize_plan_data(
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_flags: list[str],
) -> dict[str, Any]:
    sessions_markdown = []
    for session in training_plan["sessions"]:
        exercise_lines = "\n".join(
            f"  - {exercise['name']}: {exercise['sets']} x {exercise['reps']}"
            for exercise in session["exercises"]
        )
        sessions_markdown.append(
            f"### Day {session['day']} — {session['name']}\n"
            f"Focus: {session['focus']}\n"
            f"{exercise_lines}"
        )

    feedback_section = ""
    if verification_feedback:
        feedback_section = f"\n## Verification Feedback Applied\n\n{verification_feedback}\n"

    evidence_section = ""
    if evidence_summary:
        evidence_section = f"\n## Evidence Summary\n\n{evidence_summary}\n"

    safety_section = ""
    if safety_flags:
        safety_lines = "\n".join(f"- {flag}" for flag in safety_flags)
        safety_section = f"\n## Safety Flags\n\n{safety_lines}\n"

    draft_plan = (
        "# Fitness Plan Draft\n\n"
        "## Macro Targets\n\n"
        f"- Calories: {macro_targets['calories']} kcal\n"
        f"- Protein: {macro_targets['protein_g']} g\n"
        f"- Carbs: {macro_targets['carbs_g']} g\n"
        f"- Fat: {macro_targets['fat_g']} g\n\n"
        "## Training Plan\n\n"
        f"Split: {training_plan['split']} ({training_plan['goal']})\n\n"
        f"{chr(10).join(sessions_markdown)}"
        f"{evidence_section}"
        f"{feedback_section}"
        f"{safety_section}"
    )
    return {"draft_plan": draft_plan}


def write_fitness_artifacts(
    workspace_path: str,
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
    draft_plan: str,
    safety_flags: list[str],
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    calculations = {
        "macro_targets": macro_targets,
        "training_plan_summary": {
            "split": training_plan["split"],
            "goal": training_plan["goal"],
            "weekly_sets": training_plan["weekly_sets"],
            "sessions": len(training_plan["sessions"]),
        },
    }
    vfs.write("fitness/calculations.json", json.dumps(calculations, indent=2))
    vfs.write("fitness/safety_flags.json", json.dumps(safety_flags, indent=2))
    vfs.write("fitness/final_plan.md", draft_plan)
