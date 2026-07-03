import json
from pathlib import Path
from typing import Any

from core.agents.rerun import STRUCTURAL_ISSUE_MARKERS
from core.profile.extraction import extract_profile_from_query
from core.profile.normalize import merge_profile_sources
from core.profile.schema import (
    CONSTRAINT_FIELDS,
    GOAL_REQUIRED_FIELDS,
    PROFILE_FIELDS,
    REQUIRED_PROFILE_FIELDS,
    ExtractedProfile,
)
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.vfs import VFS

_PROFILE_LLM_FIELDS: tuple[str, ...] = (*PROFILE_FIELDS, *CONSTRAINT_FIELDS)


def compact_profile_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    """Return canonical profile fields for LLM payloads, excluding query and metadata."""
    return {
        field_name: profile[field_name]
        for field_name in _PROFILE_LLM_FIELDS
        if field_name in profile and profile.get(field_name) not in (None, "")
    }


def resolve_extraction_query(query: str, user_profile: dict[str, Any]) -> str:
    """Use only the latest user message when HITL resume appends clarifications to query."""
    if not user_profile:
        return query
    if "\n" in query:
        latest = query.rsplit("\n", 1)[-1].strip()
        if latest:
            return latest
    return query


def build_planning_payload(
    *,
    profile: dict[str, Any],
    query: str,
    request_type: str | None,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Build a deduplicated payload for the Planning Agent LLM call."""
    compact_profile = compact_profile_for_llm(profile)
    payload: dict[str, Any] = {"profile": compact_profile}
    stripped_query = query.strip()
    if stripped_query:
        payload["query"] = stripped_query
    if request_type:
        payload["request_type"] = request_type
    extra_constraints = {
        key: value
        for key, value in constraints.items()
        if key not in compact_profile and value not in (None, "")
    }
    if extra_constraints:
        payload["constraints"] = extra_constraints
    return payload


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


def _should_skip_profile_extraction(
    user_profile: dict[str, Any], constraints: dict[str, Any]
) -> bool:
    """Skip LLM extraction when orchestration already has a complete profile."""
    candidate = {**user_profile, **constraints}
    return not validate_profile_data(candidate)["requires_hitl"]


def should_use_llm_profile_extraction(
    user_profile: dict[str, Any], constraints: dict[str, Any]
) -> bool:
    """Return True when profile extraction will invoke the LLM extractor."""
    return not _should_skip_profile_extraction(user_profile, constraints)


def build_profile(
    query: str, user_profile: dict[str, Any], constraints: dict[str, Any]
) -> dict[str, Any]:
    if _should_skip_profile_extraction(user_profile, constraints):
        extracted = ExtractedProfile()
    else:
        extraction_query = resolve_extraction_query(query, user_profile)
        extracted = extract_profile_from_query(extraction_query)
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


def load_stored_profile(workspace_path: str) -> dict[str, Any]:
    """Load the profile snapshot persisted by planning."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("plan/profile.json"):
        return {}
    return json.loads(vfs.read("plan/profile.json"))


_ISSUE_TASK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "missing_macro_targets": ("macro", "nutrition", "caloric", "protein"),
    "training_day_count_mismatch": ("volume", "frequency", "training", "days", "week"),
    "missing_training_plan": ("training", "workout", "program"),
    "draft_missing": ("training", "workout", "program"),
}


def load_structural_issues(workspace_path: str) -> list[str]:
    """Load structural consistency issues from the latest verification report."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("verify/verification_v1.json"):
        return []
    report = json.loads(vfs.read("verify/verification_v1.json"))
    issues = report.get("consistency", {}).get("issues", [])
    if not isinstance(issues, list):
        return []
    return [
        issue
        for issue in issues
        if isinstance(issue, str) and any(marker in issue for marker in STRUCTURAL_ISSUE_MARKERS)
    ]


def execution_plan_covers_issues(plan: ExecutionPlan, issues: list[str]) -> bool:
    """Return True when every structural issue has a matching keyword in plan tasks."""
    if not issues:
        return True
    task_text = " ".join(task.task.lower() for task in plan.tasks)
    for issue in issues:
        markers = [marker for marker in STRUCTURAL_ISSUE_MARKERS if marker in issue]
        for marker in markers:
            keywords = _ISSUE_TASK_KEYWORDS.get(marker, ())
            if keywords and not any(keyword in task_text for keyword in keywords):
                return False
    return True


def profile_matches_stored_profile(profile: dict[str, Any], workspace_path: str) -> bool:
    """Return True when the current profile matches the planning VFS snapshot."""
    stored = load_stored_profile(workspace_path)
    if not stored:
        return False
    return compact_profile_for_llm(profile) == compact_profile_for_llm(stored)


def should_reuse_execution_plan(
    route_decision: str | None,
    workspace_path: str,
    profile: dict[str, Any],
) -> bool:
    """Skip XHIGH plan generation on REPLAN when the stored plan still fits the profile."""
    if route_decision != "REPLAN":
        return False
    if not has_execution_plan(workspace_path):
        return False
    if not profile_matches_stored_profile(profile, workspace_path):
        return False
    plan = load_execution_plan(workspace_path)
    issues = load_structural_issues(workspace_path)
    return execution_plan_covers_issues(plan, issues)


def load_execution_plan_from_vfs(workspace_path: str) -> dict[str, Any]:
    """Load persisted execution plan fields without invoking the Planning Agent."""
    plan = load_execution_plan(workspace_path)
    todos = execution_plan_to_todo_strings(plan)
    return {
        "todos": todos,
        "execution_plan": plan.model_dump(),
        "planning_output": plan.plan_markdown,
        "requires_hitl": False,
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
