"""Training volume and schedule.

Whether the week is trainable. This rule reads the plan against the *profile*, where
task 5.1 reads it against the template: the plan trains the days a week the user says they
can, and the prescribed work stays inside sane bounds — sets per exercise, sets per day,
weekly sets per muscle group, and reps that parse and fall in the slot's ``rep_range``.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import VerificationIssue


def check_volume(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan's schedule and training volume are within bounds."""

    raise NotImplementedError("task 5.3")
