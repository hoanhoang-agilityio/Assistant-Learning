"""Test helpers for seeding planning VFS artifacts without calling the LLM."""

from typing import Any

from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.planning.utils import build_default_execution_plan, seed_execution_plan

__all__ = ["build_default_execution_plan", "default_execution_plan", "seed_execution_plan"]


def default_execution_plan(profile: dict[str, Any] | None = None) -> ExecutionPlan:
    """Alias for the core default execution plan builder."""
    return build_default_execution_plan(profile)
