"""Fixed tables the application is wired from, kept out of the code that reads them."""

from src.constants.routes import (
    FAITHFULNESS_ROUTES,
    GUARD_ROUTES,
    HITL_AGENT_ROUTES,
    SUPERVISOR_ROUTES,
    USER_AGENT_ROUTES,
    VERIFICATION_ROUTES,
)
from src.constants.steps import STEP_LABELS

__all__ = [
    "FAITHFULNESS_ROUTES",
    "GUARD_ROUTES",
    "HITL_AGENT_ROUTES",
    "STEP_LABELS",
    "SUPERVISOR_ROUTES",
    "USER_AGENT_ROUTES",
    "VERIFICATION_ROUTES",
]
