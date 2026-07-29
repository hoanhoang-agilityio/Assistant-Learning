"""Shared compact serializers for LLM request payloads across subgraphs."""

from typing import TYPE_CHECKING, Any

from core.profile.schema import CONSTRAINT_FIELDS, PROFILE_FIELDS

if TYPE_CHECKING:
    from core.profile.goal_spec import GoalSpec

_PROFILE_LLM_FIELDS: tuple[str, ...] = (*PROFILE_FIELDS, *CONSTRAINT_FIELDS)

_GOAL_SPEC_LLM_FIELDS: tuple[str, ...] = (
    "goal_archetype",
    "weekly_rate_kg",
    "weight_delta_kg",
    "goal_direction",
    "feasibility_level",
)

_MACRO_TARGET_LLM_FIELDS: tuple[str, ...] = (
    "bmr",
    "tdee",
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
)


def compact_profile_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    """Return canonical raw profile fields for LLM payloads, excluding query and metadata."""
    return {
        field_name: profile[field_name]
        for field_name in _PROFILE_LLM_FIELDS
        if field_name in profile and profile.get(field_name) not in (None, "")
    }


def compact_goal_spec_for_llm(goal_spec: "GoalSpec") -> dict[str, Any]:
    """Return non-null GoalSpec fields for LLM goal-context payloads.

    The single place callers (planning, research) pull derived goal metrics from for LLM
    payloads, instead of each hand-picking the same keys out of an ad hoc enriched dict.
    """
    dumped = goal_spec.model_dump()
    return {
        field_name: dumped[field_name]
        for field_name in _GOAL_SPEC_LLM_FIELDS
        if dumped.get(field_name) not in (None, "")
    }


def compact_execution_plan_for_llm(
    plan: Any,
    *,
    include_task_rationale: bool = True,
) -> dict[str, Any] | None:
    """Return execution plan fields needed by downstream LLM calls (no plan_markdown).

    Returns None when `plan` is None -- an execution plan is optional context (e.g. Fitness
    reached directly from a build_plan intent with no prior Planning/Research hop), not a
    required one, so absence must round-trip cleanly instead of being coerced into a fake
    empty plan the dict branch below would then reject for lacking "tasks".
    """
    from core.planning.schema import ExecutionPlan

    if plan is None:
        return None
    if isinstance(plan, ExecutionPlan):
        tasks = (
            [task.model_dump() for task in plan.tasks]
            if include_task_rationale
            else [{"order": task.order, "task": task.task} for task in plan.tasks]
        )
        return {
            "plan_rationale": plan.plan_rationale,
            "tasks": tasks,
        }
    if not isinstance(plan, dict):
        raise TypeError("plan must be ExecutionPlan or dict")
    raw_tasks = plan["tasks"]
    if include_task_rationale:
        tasks = raw_tasks
    else:
        tasks = [{"order": task["order"], "task": task["task"]} for task in raw_tasks]
    return {
        "plan_rationale": plan["plan_rationale"],
        "tasks": tasks,
    }


def compact_macro_targets_for_llm(macro_targets: dict[str, Any]) -> dict[str, Any]:
    """Return nutrition numbers only; goal/activity_level belong in profile."""
    return {
        field_name: macro_targets[field_name]
        for field_name in _MACRO_TARGET_LLM_FIELDS
        if field_name in macro_targets and macro_targets.get(field_name) not in (None, "")
    }


def compact_structured_findings(structured_findings: Any) -> dict[str, Any] | None:
    """Return a compact research-findings payload for the fitness planner."""
    from core.subgraphs.research.schema import ResearchFindings

    if structured_findings is None:
        return None
    if not isinstance(structured_findings, ResearchFindings):
        raise TypeError("structured_findings must be ResearchFindings or None")
    return {
        "consensus": structured_findings.consensus,
        "key_findings": [item.model_dump() for item in structured_findings.key_findings[:5]],
        "limitations": structured_findings.limitations[:2],
        "recommended_sources": structured_findings.recommended_sources[:5],
    }


def compact_evidence_for_llm(
    evidence: list[dict[str, Any]],
    *,
    limit: int = 5,
    content_chars: int = 800,
) -> list[dict[str, Any]]:
    """Truncate raw evidence docs before they can reach any LLM payload.

    research/findings.json stores evidence content untruncated (it's an
    archival artifact, not itself a prompt). Any code path that hands that
    evidence to an LLM call — today or in the future — must go through this
    first, matching the truncation research_agent.py's own synthesis/eval
    calls already apply (see build_synthesis_llm_extra/build_eval_llm_extra).
    """
    return [
        {
            "url": item.get("url"),
            "content": str(item.get("content", ""))[:content_chars],
        }
        for item in evidence[:limit]
    ]
