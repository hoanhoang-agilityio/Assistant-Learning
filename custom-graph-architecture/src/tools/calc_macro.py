"""``calc_macro``: the calorie and macro targets a profile works out to."""

from typing import Any

from langchain.tools import ToolRuntime, tool

from src.core.langgraph.tools.context import context_profile
from src.enums import FitnessGoal
from src.schemas import CoachContext
from src.services.nutrition import calc_macros

NO_PROFILE = (
    "no profile is on record, and the targets cannot be computed without the user's age,"
    " sex, height, weight and activity level; ask for them instead of estimating"
)


@tool
def calc_macro(
    runtime: ToolRuntime[CoachContext, Any], goal: FitnessGoal | None = None
) -> dict:
    """Return the user's daily calorie and macro targets from their saved profile.

    Pass `goal` only when answering about a goal different from the user's
    current training goal.
    """

    # Body metrics come from the runtime, not the model. This prevents the
    # model from supplying hallucinated values and uses the data the user
    # has already provided.
    profile = context_profile(runtime)
    if profile is None:
        return {"error": NO_PROFILE}

    return calc_macros(profile, goal=goal).model_dump(mode="json")
