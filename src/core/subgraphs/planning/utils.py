import json
from pathlib import Path
from typing import Any

from core.profile.extraction import extract_profile_from_query
from core.profile.normalize import merge_profile_sources
from core.profile.schema import (
    CONSTRAINT_FIELDS,
    GOAL_REQUIRED_FIELDS,
    PROFILE_FIELDS,
    REQUIRED_PROFILE_FIELDS,
)
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
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


def execution_plan_to_todo_strings(plan: ExecutionPlan) -> list[str]:
    """Derive ordered task strings from an execution plan."""
    ordered = sorted(plan.tasks, key=lambda task: task.order)
    return [task.task for task in ordered]


def has_execution_plan(workspace_path: str) -> bool:
    """Return whether a canonical execution plan exists on the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    return vfs.exists("plan/execution_plan.json")


def load_execution_plan(workspace_path: str) -> ExecutionPlan:
    """Load the canonical execution plan from the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    raw = json.loads(vfs.read("plan/execution_plan.json"))
    return ExecutionPlan.model_validate(raw)


def persist_execution_plan(
    profile: dict[str, Any],
    plan: ExecutionPlan,
    workspace_path: str,
) -> dict[str, Any]:
    """Persist execution plan artifacts to the run workspace VFS."""
    todos = execution_plan_to_todo_strings(plan)
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("plan/execution_plan.json", plan.model_dump_json(indent=2))
    vfs.write("plan/plan.md", plan.plan_markdown)
    vfs.write("plan/profile.json", json.dumps(profile, indent=2))
    # Deprecated: derived compatibility shim; migrate consumers to execution_plan.json.
    vfs.write("plan/todos.json", json.dumps(todos, indent=2))
    return {
        "todos": todos,
        "execution_plan": plan.model_dump(),
        "planning_output": plan.plan_markdown,
        "requires_hitl": False,
    }


def build_default_execution_plan(profile: dict[str, Any] | None = None) -> ExecutionPlan:
    """Build a deterministic fallback execution plan for tests and benchmarks."""
    goal = (profile or {}).get("goal", "general_fitness")
    return ExecutionPlan(
        plan_rationale=(
            f"Research plan tailored for {goal} with evidence gathering and source verification."
        ),
        tasks=[
            PlanTask(
                order=1,
                task=f"Research evidence-based training principles for {goal}",
                rationale=f"Establish foundational evidence for the user's {goal} goal.",
            ),
            PlanTask(
                order=2,
                task="Gather activity-level training volume recommendations",
                rationale="Match training frequency to the user's current activity level.",
            ),
            PlanTask(
                order=3,
                task="Collect macro and recovery guidance aligned with user constraints",
                rationale="Support nutrition and recovery decisions with credible sources.",
            ),
            PlanTask(
                order=4,
                task="Verify fitness-domain credibility of selected sources",
                rationale="Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            f"# Planning Summary\n\n"
            f"- Goal: {goal}\n"
            f"- Tasks: 4 research-oriented steps\n"
            f"- Rationale: Tailored evidence plan for {goal}\n"
        ),
    )


def seed_execution_plan(
    workspace_path: str,
    profile: dict[str, Any],
    plan: ExecutionPlan | None = None,
) -> ExecutionPlan:
    """Seed planning VFS artifacts without calling the Planning Agent."""
    resolved_plan = plan or build_default_execution_plan(profile)
    persist_execution_plan(profile, resolved_plan, workspace_path)
    return resolved_plan


def has_planning_todos(workspace_path: str) -> bool:
    """Return whether planning artifacts exist (delegates to execution plan)."""
    return has_execution_plan(workspace_path)


def load_planning_todos(workspace_path: str) -> list[str]:
    """Load ordered task strings from the execution plan (legacy todos.json wrapper)."""
    if not has_execution_plan(workspace_path):
        return []
    return execution_plan_to_todo_strings(load_execution_plan(workspace_path))
