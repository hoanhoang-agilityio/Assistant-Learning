"""``load_template``: the training week's structure, before any exercise is chosen."""

from langchain_core.tools import tool

from src.enums import FitnessGoal
from src.schemas.domain.profile import MAX_TRAINING_DAYS, MIN_TRAINING_DAYS
from src.services.catalogue import find_template

NO_TEMPLATE = (
    "no template is available; build the training week from the user's profile instead"
)


def clamp_training_days(days_per_week: int) -> int:
    """Hold the requested week inside the range a profile can express."""

    return min(max(days_per_week, MIN_TRAINING_DAYS), MAX_TRAINING_DAYS)


@tool
async def load_template(goal: FitnessGoal, days_per_week: int) -> dict:
    """Return the training week template that best fits a goal and a weekly frequency."""

    days = clamp_training_days(days_per_week)
    template = await find_template(goal, days)

    if template is None:
        return {"error": NO_TEMPLATE}

    return template.model_dump(mode="json")
