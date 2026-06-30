import json
from pathlib import Path
from typing import Any

from core.profile.extraction import extract_profile_from_query
from core.profile.labels import format_activity_label, format_goal_label
from core.profile.normalize import merge_profile_sources
from core.profile.schema import (
    CONSTRAINT_FIELDS,
    GOAL_REQUIRED_FIELDS,
    PROFILE_FIELDS,
    REQUIRED_PROFILE_FIELDS,
)
from core.vfs import VFS


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
    extracted = extract_profile_from_query(query)
    return merge_profile_sources(
        query=query,
        user_profile=user_profile,
        constraints=constraints,
        extracted=extracted,
    )


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
