"""Macro consistency.

Arithmetic the agent is not trusted to do: the macros have to add up to the calorie target
(``MacroTargets.calories``), the calorie target has to match what ``services.nutrition``
computes from the profile, the plan's goal has to be the profile's goal, and the target
has to sit above the calorie floor for the user's sex.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import VerificationIssue


def check_macros(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan's calories and macros agree with each other and with the profile."""

    raise NotImplementedError("task 5.2")
