import json
import re
from pathlib import Path
from typing import Any

from core.profile.labels import format_activity_label, format_goal_label
from core.vfs import VFS

REQUIRED_PROFILE_FIELDS = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "activity_level",
    "goal",
)
GOAL_REQUIRED_FIELDS = {
    "fat_loss": ("target_weight_kg",),
}


def extract_sex(profile: dict[str, Any], query: str) -> None:
    if "sex" in profile:
        return
    query_lower = query.lower()
    if re.search(r"\bfemale\b|\bwoman\b", query_lower):
        profile["sex"] = "female"
        return
    if re.search(r"\bmale\b|\bman\b", query_lower):
        profile["sex"] = "male"


def extract_age(profile: dict[str, Any], query: str) -> None:
    if "age" in profile:
        return
    query_lower = query.lower()
    age_patterns = (
        r"age\s+(\d{1,2})\b",
        r"(?:^|[\s,])i'?m\s+(\d{1,2})\b",
        r"(\d{2})\s*(?:years?\s*old|yo|y\.o\.)",
        r"(?:^|[\s,])(\d{1,2})\s*,",
    )
    for pattern in age_patterns:
        age_match = re.search(pattern, query_lower)
        if age_match:
            profile["age"] = int(age_match.group(1))
            return


def extract_height(profile: dict[str, Any], query: str) -> None:
    if "height_cm" in profile:
        return
    height_match = re.search(r"(\d{2,3})\s*cm", query.lower())
    if height_match:
        profile["height_cm"] = int(height_match.group(1))


def extract_current_weight(profile: dict[str, Any], query: str) -> None:
    if "current_weight_kg" in profile:
        return
    query_lower = query.lower()
    labeled_match = re.search(r"weight\s+(\d{2,3}(?:\.\d+)?)\s*kg", query_lower)
    if labeled_match:
        profile["current_weight_kg"] = float(labeled_match.group(1))
        return
    weight_matches = re.findall(r"(\d{2,3}(?:\.\d+)?)\s*kg", query_lower)
    if weight_matches:
        profile["current_weight_kg"] = float(weight_matches[0])


def extract_target_weight(profile: dict[str, Any], query: str) -> None:
    if "target_weight_kg" in profile:
        return
    query_lower = query.lower()
    gain_match = re.search(r"gain\s+(\d+(?:\.\d+)?)\s*kg", query_lower)
    if gain_match:
        gain_kg = float(gain_match.group(1))
        current = profile.get("current_weight_kg")
        if current is not None:
            profile["target_weight_kg"] = float(current) + gain_kg
            return
    lose_match = re.search(r"lose\s+(\d+(?:\.\d+)?)\s*kg", query_lower)
    if lose_match:
        loss_kg = float(lose_match.group(1))
        current = profile.get("current_weight_kg")
        if current is not None:
            profile["target_weight_kg"] = float(current) - loss_kg
            return
    goal_weight_match = re.search(r"goal[:\s]+(\d{2,3})\s*kg", query_lower)
    if goal_weight_match:
        profile["target_weight_kg"] = float(goal_weight_match.group(1))
        return
    weight_matches = re.findall(r"(\d{2,3})\s*kg", query_lower)
    if len(weight_matches) > 1:
        profile["target_weight_kg"] = float(weight_matches[1])


def extract_activity(profile: dict[str, Any], query: str) -> None:
    query_lower = query.lower()
    days_patterns = (
        r"(?:training|train)\s+(\d+)\s*days?",
        r"(\d+)\s*days?\s*(?:per week|a week|/week|weekly)",
    )
    for pattern in days_patterns:
        days_match = re.search(pattern, query_lower)
        if days_match:
            days = min(int(days_match.group(1)), 6)
            profile["days_per_week"] = days
            profile["activity_level"] = f"gym_{days}x_week"
            return
    if "activity_level" in profile:
        return
    gym_match = re.search(r"gym\s*(\d+)x", query_lower)
    if gym_match:
        profile["activity_level"] = f"gym_{gym_match.group(1)}x_week"
        return
    if "sedentary" in query_lower:
        profile["activity_level"] = "sedentary"


def extract_goal(profile: dict[str, Any], query: str) -> None:
    if "goal" in profile:
        return
    query_lower = query.lower()
    if re.search(r"gain\s+\d+(?:\.\d+)?\s*kg", query_lower):
        profile["goal"] = "muscle_gain"
        return
    if re.search(r"lose\s+\d+(?:\.\d+)?\s*kg", query_lower):
        profile["goal"] = "fat_loss"
        return
    if any(keyword in query_lower for keyword in ("lose weight", "fat loss", "cutting")):
        profile["goal"] = "fat_loss"
        return
    if any(keyword in query_lower for keyword in ("muscle", "hypertrophy", "bulk")):
        profile["goal"] = "muscle_gain"
        return
    if any(keyword in query_lower for keyword in ("strength", "powerlifting")):
        profile["goal"] = "strength"
        return
    if "endurance" in query_lower or "marathon" in query_lower:
        profile["goal"] = "endurance"


EXTRACTORS = (
    extract_sex,
    extract_age,
    extract_height,
    extract_current_weight,
    extract_target_weight,
    extract_activity,
    extract_goal,
)


CONSTRAINT_FIELDS = ("days_per_week", "equipment", "session_duration_minutes", "high_protein")
PROFILE_FIELDS = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
    "activity_level",
    "goal",
)


def profile_to_orchestration_updates(
    profile: dict[str, Any],
    *,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Map an extracted planning profile onto orchestration user_profile/constraints."""
    user_profile = {field: profile[field] for field in PROFILE_FIELDS if field in profile}
    if missing_fields is not None:
        user_profile["missing_fields"] = missing_fields
    constraints = {field: profile[field] for field in CONSTRAINT_FIELDS if field in profile}
    return {"user_profile": user_profile, "constraints": constraints}


def build_profile(
    query: str, user_profile: dict[str, Any], constraints: dict[str, Any]
) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "query": query,
        **user_profile,
        **constraints,
    }
    for extractor in EXTRACTORS:
        extractor(profile, query)
    return profile


def validate_profile_data(profile: dict[str, Any]) -> dict[str, Any]:
    missing_fields: list[str] = []
    for field_name in REQUIRED_PROFILE_FIELDS:
        if profile.get(field_name) in (None, ""):
            missing_fields.append(field_name)

    goal = profile.get("goal")
    if isinstance(goal, str):
        for field_name in GOAL_REQUIRED_FIELDS.get(goal, ()):
            if profile.get(field_name) in (None, ""):
                missing_fields.append(field_name)

    unique_missing_fields = sorted(set(missing_fields))
    return {
        "missing_fields": unique_missing_fields,
        "requires_hitl": bool(unique_missing_fields),
    }


def write_planning_todos(
    profile: dict[str, Any],
    request_type: str | None,
    workspace_path: str,
) -> dict[str, Any]:
    goal = profile.get("goal", "general_fitness")
    activity_level = profile.get("activity_level", "unspecified")
    goal_label = format_goal_label(str(goal))
    activity_label = format_activity_label(str(activity_level))
    todos = [
        f"Research evidence-based training principles for {goal_label.lower()}",
        f"Gather recommendations for activity level: {activity_label}",
        "Collect macro and recovery guidance aligned with user constraints",
        "Verify fitness-domain credibility of selected sources",
    ]
    if request_type == "macro_calculation":
        todos.insert(0, "Research macro calculation methods for user goal")

    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("plan/profile.json", json.dumps(profile, indent=2))
    vfs.write("plan/todos.json", json.dumps(todos, indent=2))
    planning_output = (
        f"# Planning Summary\n\n"
        f"- Goal: {goal_label}\n"
        f"- Activity level: {activity_label}\n"
        f"- Todos: {len(todos)}\n"
    )
    vfs.write("plan/plan.md", planning_output)

    return {
        "todos": todos,
        "planning_output": planning_output,
        "requires_hitl": False,
    }


def has_planning_todos(workspace_path: str) -> bool:
    """Return whether planning todos exist on the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    return vfs.exists("plan/todos.json")


def load_planning_todos(workspace_path: str) -> list[str]:
    """Load planning todos from the run workspace VFS."""
    if not has_planning_todos(workspace_path):
        return []
    vfs = VFS.for_run(Path(workspace_path))
    todos = json.loads(vfs.read("plan/todos.json"))
    if not isinstance(todos, list):
        raise ValueError("plan/todos.json must contain a JSON list")
    return [str(todo) for todo in todos]
