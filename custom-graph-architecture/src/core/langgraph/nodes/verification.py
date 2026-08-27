"""The ``deterministic_verification`` node: run the rules, count the retries, route."""

from typing import TypedDict

from pydantic import ValidationError

from src.core.configs.config import settings
from src.core.langgraph.verification import verify_plan
from src.schemas import (
    CheckName,
    GraphState,
    TrainingPlan,
    UserProfile,
    VerificationIssue,
    VerificationResult,
    VerificationRoute,
)

NO_PLAN_MESSAGE = (
    "No plan was returned. Produce the complete training plan using the structured "
    "output schema."
)
INVALID_PLAN_MESSAGE = (
    "The plan did not match the plan schema and could not be checked. Return a complete "
    "plan using the structured output schema."
)
UNVERIFIABLE_PROFILE_MESSAGE = (
    "The stored profile could not be read, so the plan cannot be verified against the "
    "user it is for."
)


class VerificationUpdate(TypedDict):
    """The state ``deterministic_verification`` writes."""

    verification_result: dict | None
    coach_retry_count: int


def _blocked(message: str, field: str) -> VerificationResult:
    """A verdict for a plan no rule could run on: one error, so the gate fails."""

    return VerificationResult(
        issues=[
            VerificationIssue(
                check=CheckName.COMPLETENESS, message=message, field=field
            )
        ]
    )


async def _verify(state: GraphState) -> VerificationResult:
    """Run the gate over the plan in state, or report why it could not be run."""

    plan_data = state.get("plan")
    if not plan_data:
        return _blocked(NO_PLAN_MESSAGE, "plan")

    try:
        plan = TrainingPlan.model_validate(plan_data)
    except ValidationError:
        return _blocked(INVALID_PLAN_MESSAGE, "plan")

    try:
        profile = UserProfile.model_validate(state.get("profile") or {})
    except ValidationError:
        return _blocked(UNVERIFIABLE_PROFILE_MESSAGE, "profile")

    return await verify_plan(plan, profile)


async def deterministic_verification(state: GraphState) -> VerificationUpdate:
    """Check the generated plan against every deterministic rule."""

    result = await _verify(state)

    if result.passed:
        return {"verification_result": None, "coach_retry_count": 0}

    return {
        "verification_result": result.model_dump(mode="json"),
        "coach_retry_count": state.get("coach_retry_count", 0) + 1,
    }


def route_after_verification(state: GraphState) -> VerificationRoute:
    """Send a good plan on to review, a bad one back to the coach, or give up."""

    if not state.get("verification_result"):
        return VerificationRoute.PASS
    if state.get("coach_retry_count", 0) >= settings.COACH_MAX_RETRIES:
        return VerificationRoute.EXHAUSTED
    return VerificationRoute.RETRY
