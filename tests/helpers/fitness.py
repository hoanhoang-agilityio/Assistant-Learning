"""Test helpers for seeding fitness planner output without calling the LLM."""

from typing import Any

from core.capabilities.fitness.utils import build_default_structured_workout

__all__ = ["build_default_structured_workout", "default_structured_workout"]


def default_structured_workout(
    profile: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
):
    """Alias for the core default structured workout builder."""
    return build_default_structured_workout(profile, constraints)
