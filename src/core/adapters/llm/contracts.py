"""Explicit LLM payload contracts and forbidden-field validation."""

from __future__ import annotations

from typing import Any

FORBIDDEN_PROFILE_KEYS: frozenset[str] = frozenset({"query", "missing_fields"})

FORBIDDEN_RESEARCH_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"plan_markdown", "planning_output", "todos"}
)

FORBIDDEN_FITNESS_PAYLOAD_KEYS: frozenset[str] = frozenset({"constraints"})


def assert_no_forbidden_keys(payload: dict[str, Any], forbidden: frozenset[str]) -> None:
    """Raise when forbidden top-level keys are present."""
    present = forbidden.intersection(payload.keys())
    if present:
        raise ValueError(f"Forbidden payload keys present: {sorted(present)}")


def assert_compact_profile_contract(profile: dict[str, Any]) -> None:
    """Validate profile sub-payload contract."""
    present = FORBIDDEN_PROFILE_KEYS.intersection(profile.keys())
    if present:
        raise ValueError(f"Forbidden profile keys present: {sorted(present)}")


def assert_compact_execution_plan_contract(plan_payload: dict[str, Any]) -> None:
    """Validate compact execution plan sub-payload contract."""
    if "plan_markdown" in plan_payload:
        raise ValueError("plan_markdown is forbidden in compact execution plan payloads")
    if "tasks" not in plan_payload or "plan_rationale" not in plan_payload:
        raise ValueError("tasks and plan_rationale are required in execution plan payloads")


def validate_research_context_payload(payload: dict[str, Any]) -> None:
    """Validate Research Agent LLM payload contract."""
    assert_no_forbidden_keys(payload, FORBIDDEN_RESEARCH_PAYLOAD_KEYS)
    assert_compact_profile_contract(payload.get("profile", {}))
    if "plan_markdown" in payload:
        raise ValueError("plan_markdown is forbidden in research payloads")


def validate_fitness_planner_payload(payload: dict[str, Any]) -> None:
    """Validate Fitness Planner LLM payload contract."""
    assert_no_forbidden_keys(payload, FORBIDDEN_FITNESS_PAYLOAD_KEYS)
    assert_compact_profile_contract(payload.get("profile", {}))
    execution_plan = payload.get("execution_plan")
    if isinstance(execution_plan, dict):
        assert_compact_execution_plan_contract(execution_plan)
    macro_targets = payload.get("macro_targets", {})
    if isinstance(macro_targets, dict):
        for key in ("goal", "activity_level"):
            if key in macro_targets:
                raise ValueError(f"{key} must not be duplicated in macro_targets")


# ROI-ranked implementation order (impact / risk). High-risk items excluded from phase 1.
OPTIMIZATION_ROI_RANKING: tuple[dict[str, str], ...] = (
    {
        "rank": "1",
        "optimization": "Fitness omit plan_markdown via compact_execution_plan_for_llm",
        "risk": "low",
    },
    {
        "rank": "2",
        "optimization": "Fitness compact profile and forbid profile.query",
        "risk": "low",
    },
    {
        "rank": "3",
        "optimization": "Planning state duplicate removal",
        "risk": "low",
    },
    {
        "rank": "4",
        "optimization": "Research state todos removal",
        "risk": "low",
    },
    {
        "rank": "5",
        "optimization": "Fitness constraints/training_constraints dedupe",
        "risk": "medium",
    },
    {
        "rank": "6",
        "optimization": "LLM payload debug instrumentation",
        "risk": "low",
    },
    {
        "rank": "7",
        "optimization": "Deterministic plan_markdown rendering",
        "risk": "medium",
    },
    {
        "rank": "8",
        "optimization": "Research evidence/context reduction",
        "risk": "high",
    },
)
