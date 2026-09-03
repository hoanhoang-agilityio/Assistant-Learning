"""Tools for ``user_agent``: read the user's profile, and write one field at a time."""

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.schemas import UserAgentContext, UserProfile
from src.services.profile import load_user_context, save_profile

NO_PROFILE_RECORDED = "no profile is on record for this user yet"


@tool(response_format="content_and_artifact")
async def get_user_profile(
    runtime: ToolRuntime[UserAgentContext, Any],
) -> tuple[str, dict]:
    """Return the user's stored training profile.

    Call this before answering questions about the user's own profile,
    or before deciding whether newly stated information is new or a correction.
    """

    context = await load_user_context(runtime.context.user_id)
    if not context.profile:
        return NO_PROFILE_RECORDED, {"profile": None}

    return json.dumps(context.profile, ensure_ascii=False), {"profile": context.profile}


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
