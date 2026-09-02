"""``get_plan``: the training plan on record for the user, as the coach's own read of it."""

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.schemas import CoachContext, TrainingPlan
from src.services.plan_presentation import render_plan_markdown
from src.services.profile import load_current_plan
from src.tools.context import context_user_id

NO_PLAN_RECORDED = "no training plan is on record for this user yet"


@tool(response_format="content_and_artifact")
async def get_plan(runtime: ToolRuntime[CoachContext, Any]) -> tuple[str, dict]:
    """Return the training plan stored for the user, or say that none is on record.

    Call this before answering anything about the plan the user already has, and before
    revising a plan the conversation is not already holding a draft of.
    """

    # The user is read from the runtime rather than taken as an argument, so the model
    # cannot ask for a different user's plan.
    user_id = context_user_id(runtime)
    if not user_id:
        return NO_PLAN_RECORDED, {"plan": None}

    plan = await load_current_plan(user_id)
    if not plan:
        return NO_PLAN_RECORDED, {"plan": None}

    # Rendered rather than dumped: the stored plan names its exercises by catalogue id,
    # which is what the answer must not repeat back to the user. A plan the renderer
    # cannot resolve — an older schema, a catalogue row since deleted — is still the
    # user's plan, so it degrades to the raw record rather than to no answer at all.
    try:
        content = await render_plan_markdown(TrainingPlan.model_validate(plan))
    except Exception:
        content = json.dumps(plan, ensure_ascii=False)

    return content, {"plan": plan}
