"""Shared compact serializers for LLM request payloads across subgraphs."""

from typing import Any

from core.profile.schema import CONSTRAINT_FIELDS, PROFILE_FIELDS

_PROFILE_LLM_FIELDS: tuple[str, ...] = (*PROFILE_FIELDS, *CONSTRAINT_FIELDS)

_MACRO_TARGET_LLM_FIELDS: tuple[str, ...] = (
    "bmr",
    "tdee",
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
)


def compact_profile_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    """Return canonical profile fields for LLM payloads, excluding query and metadata."""
    compact = {
        field_name: profile[field_name]
        for field_name in _PROFILE_LLM_FIELDS
        if field_name in profile and profile.get(field_name) not in (None, "")
    }
    if "days_per_week" in compact and "activity_level" in compact:
        del compact["activity_level"]
    return compact


def compact_execution_plan_for_llm(
    plan: Any,
    *,
    include_task_rationale: bool = True,
) -> dict[str, Any]:
    """Return execution plan fields needed by downstream LLM calls (no plan_markdown)."""
    from core.subgraphs.planning.schema import ExecutionPlan

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
        "key_findings": structured_findings.key_findings[:3],
        "limitations": structured_findings.limitations[:2],
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
