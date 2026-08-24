"""Training volume and schedule.

Whether the week is trainable: the plan trains the days a week the profile says the user
can, day numbers run 1..n with no gaps or repeats, and the prescribed work stays inside
sane bounds — sets per exercise, sets per day, weekly sets per muscle group, and reps that
parse and fall in the slot's ``rep_range``.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import VerificationIssue


def check_volume(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan's schedule and training volume are within bounds."""

    raise NotImplementedError("task 5.3")
