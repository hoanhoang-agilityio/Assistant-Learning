"""Exercise availability and user constraints.

Whether this user can actually perform this plan. Every prescribed exercise's equipment is
covered by ``profile.available_equipment``, and every exercise satisfies the slot it claims
to fill: ``ExerciseSlot.accepts_pattern`` for the movement, and the slot's target muscles
among the exercise's primary ones — the check that a rear-delt slot did not get a lateral
raise. Difficulty above the user's level and ignored preferences are warnings, not errors.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import VerificationIssue


def check_availability(context: PlanContext) -> list[VerificationIssue]:
    """Check every prescription is available to the user and fits the slot it fills."""

    raise NotImplementedError("task 5.4")
