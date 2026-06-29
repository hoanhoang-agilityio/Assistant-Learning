import json
import re
from pathlib import Path
from typing import Any

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
    age_match = re.search(r"(\d{2})\s*(?:years?\s*old|yo|y\.o\.)", query.lower())
    if age_match:
        profile["age"] = int(age_match.group(1))


def extract_height(profile: dict[str, Any], query: str) -> None:
    if "height_cm" in profile:
        return
    height_match = re.search(r"(\d{2,3})\s*cm", query.lower())
    if height_match:
        profile["height_cm"] = int(height_match.group(1))


def extract_current_weight(profile: dict[str, Any], query: str) -> None:
    if "current_weight_kg" in profile:
        return
    weight_matches = re.findall(r"(\d{2,3})\s*kg", query.lower())
    if weight_matches:
        profile["current_weight_kg"] = float(weight_matches[0])


def extract_target_weight(profile: dict[str, Any], query: str) -> None:
    if "target_weight_kg" in profile:
        return
    query_lower = query.lower()
    goal_weight_match = re.search(r"goal[:\s]+(\d{2,3})\s*kg", query_lower)
    if goal_weight_match:
        profile["target_weight_kg"] = float(goal_weight_match.group(1))
        return
    weight_matches = re.findall(r"(\d{2,3})\s*kg", query_lower)
    if len(weight_matches) > 1:
        profile["target_weight_kg"] = float(weight_matches[1])


def extract_activity(profile: dict[str, Any], query: str) -> None:
    if "activity_level" in profile:
        return
    query_lower = query.lower()
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
    todos = [
        f"Research evidence-based training principles for {goal}",
        f"Gather recommendations for activity level: {activity_level}",
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
        f"- Goal: {goal}\n"
        f"- Activity level: {activity_level}\n"
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
