"""Tools for ``user_agent`` and ``coach_agent``: read the user's profile, and write one field at a time."""

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.schemas import CoachContext, UserAgentContext, UserProfile
from src.services.profile import (
    load_profile,
    missing_profile_fields,
    nutrition_targets,
    save_profile,
)

NO_PROFILE_RECORDED = "no profile is on record for this user yet"


@tool(response_format="content_and_artifact")
async def get_user_profile(
    runtime: ToolRuntime[UserAgentContext, Any],
) -> tuple[str, dict]:
    """Return the user's stored training profile.

    Call this before answering questions about the user's own profile,
    or before deciding whether newly stated information is new or a correction.
    """

    profile = await load_profile(runtime.context.user_id)
    if not profile:
        return NO_PROFILE_RECORDED, {"profile": None}

    return json.dumps(profile, ensure_ascii=False), {"profile": profile}


@tool(response_format="content_and_artifact")
async def get_profile_and_targets(
    runtime: ToolRuntime[CoachContext, Any],
) -> tuple[str, dict]:
    """Return the user's profile and the nutrition targets it works out to.

    Call this before building a first plan or revising the plan on record, to read the
    user's body metrics, equipment and injuries. Never call it for a question about the
    plan already on record — that needs only `get_plan`.
    """

    context = runtime.context
    profile = context.profile if isinstance(context, CoachContext) else None
    missing = missing_profile_fields(profile)
    if missing:
        return (
            f"Profile is missing required fields: {', '.join(missing)}.",
            {"profile": profile, "missing_fields": missing},
        )

    content = json.dumps(
        {"profile": profile, "nutrition_targets": nutrition_targets(profile)},
        ensure_ascii=False,
    )
    return content, {"profile": profile, "missing_fields": []}


@tool(response_format="content_and_artifact")
async def update_user_profile(
    field: str, value: Any, runtime: ToolRuntime[UserAgentContext, Any]
) -> tuple[str, dict]:
    """Save one field of the user's profile.

    Use the exact profile field name. Only call this tool after any required
    approval for overwriting an existing value has been granted.
    """

    if field not in UserProfile.model_fields:
        return f"'{field}' is not a profile field.", {"status": "invalid_field"}

    updated = await save_profile(runtime.context.user_id, {field: value})
    return (
        f"Saved {field} = {value!r}.",
        {"status": "written", "field": field, "profile": updated},
    )
