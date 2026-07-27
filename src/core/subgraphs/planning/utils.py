import json
from pathlib import Path
from typing import Any

from core.agents.rerun import STRUCTURAL_ISSUE_MARKERS
from core.llm.contracts import validate_planning_payload
from core.llm.serializers import compact_goal_spec_for_llm, compact_profile_for_llm
from core.profile.goal_spec import GoalSpec, derive_goal_spec
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.planning.templates import build_template_execution_plan
from core.subgraphs.user.utils import load_stored_profile
from core.vfs import VFS

# NOTE: `generate_plan` lives in `graph.py`, not here -- it needs both this module
# (persist_execution_plan) and `planning_agent.py` (generate_execution_plan), and
# `planning_agent.py` already imports `build_planning_payload` from this module, so defining
# it here would create a circular import (utils -> planning_agent -> utils).

__all__ = [
    "build_default_execution_plan",
    "build_planning_payload",
    "compact_profile_for_llm",
    "execution_plan_covers_issues",
    "execution_plan_to_todo_strings",
    "has_execution_plan",
    "has_planning_todos",
    "load_execution_plan",
    "load_planning_todos",
    "load_stored_profile",
    "persist_execution_plan",
    "persist_revision_feedback",
    "load_revision_feedback",
    "profile_matches_stored_profile",
    "seed_execution_plan",
    "should_reuse_execution_plan",
]


def build_planning_payload(
    *,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    query: str,
    request_type: str | None,
    constraints: dict[str, Any],
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    """Build a deduplicated payload for the Planning Agent LLM call.

    `goal_spec` must be derived by the caller (`generate_plan`) from this same `profile`,
    not recomputed here -- see the single-derivation threading rule.
    """
    compact_profile = compact_profile_for_llm(profile)
    payload: dict[str, Any] = {"profile": compact_profile}
    goal_context = {
        "horizon_weeks": profile.get("horizon_weeks"),
        **compact_goal_spec_for_llm(goal_spec),
    }
    goal_context = {key: value for key, value in goal_context.items() if value not in (None, "")}
    if goal_context:
        payload["goal_context"] = goal_context
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
    stripped_feedback = (revision_feedback or "").strip()
    if stripped_feedback:
        payload["revision_feedback"] = stripped_feedback
    validate_planning_payload(payload)
    return payload


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


def persist_revision_feedback(workspace_path: str, feedback: str) -> None:
    """Persist user revision feedback for downstream REPLAN runs."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("plan/revision_feedback.json", json.dumps({"feedback": feedback.strip()}, indent=2))


def load_revision_feedback(workspace_path: str) -> str | None:
    """Load user revision feedback from the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("plan/revision_feedback.json"):
        return None
    payload = json.loads(vfs.read("plan/revision_feedback.json"))
    feedback = payload.get("feedback")
    if not isinstance(feedback, str):
        return None
    stripped = feedback.strip()
    return stripped or None


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
    if load_revision_feedback(workspace_path):
        return False
    if not has_execution_plan(workspace_path):
        return False
    if not profile_matches_stored_profile(profile, workspace_path):
        return False
    plan = load_execution_plan(workspace_path)
    issues = load_structural_issues(workspace_path)
    return execution_plan_covers_issues(plan, issues)


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
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("plan/execution_plan.json", plan.model_dump_json(indent=2))
    vfs.write("plan/plan.md", plan.plan_markdown)
    vfs.write(
        "plan/profile.json",
        json.dumps(compact_profile_for_llm(profile), indent=2),
    )
    return {}


def build_default_execution_plan(profile: dict[str, Any] | None = None) -> ExecutionPlan:
    """Build a deterministic fallback execution plan for tests and benchmarks."""
    resolved_profile = profile or {}
    goal_spec = derive_goal_spec(resolved_profile)
    template_plan = build_template_execution_plan(resolved_profile, goal_spec)
    if template_plan is not None:
        return template_plan
    goal = resolved_profile.get("goal", "general_fitness")
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
