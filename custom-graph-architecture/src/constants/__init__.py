"""Fixed tables the application is wired from, kept out of the code that reads them."""

from src.constants.routes import (
    COACH_ROUTES,
    FAITHFULNESS_ROUTES,
    GUARD_ROUTES,
    PLAN_APPROVAL_ROUTES,
    SUPERVISOR_ROUTES,
    USER_AGENT_ROUTES,
    VERIFICATION_ROUTES,
)
from src.constants.steps import STEP_LABELS

__all__ = [
    "COACH_ROUTES",
    "FAITHFULNESS_ROUTES",
    "GUARD_ROUTES",
    "PLAN_APPROVAL_ROUTES",
    "STEP_LABELS",
    "SUPERVISOR_ROUTES",
    "USER_AGENT_ROUTES",
    "VERIFICATION_ROUTES",
]
