"""Tools for ``user_agent``: read the user's profile, and write one field at a time."""

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.schemas import UserAgentContext, UserProfile
from src.services.profile import load_user_context, save_profile

NO_PROFILE_RECORDED = "no profile is on record for this user yet"


def _is_blank(value: object) -> bool:
    """Report whether a stored field carries no usable value."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


@tool(response_format="content_and_artifact")
async def get_user_profile(
    runtime: ToolRuntime[UserAgentContext, Any],
) -> tuple[str, dict]:
    """Return the user's stored profile and current training plan.

    Call this before answering anything about the user's own data, and before deciding
    whether a field they just mentioned is new information or a correction to something
    already on file.
    """

    context = await load_user_context(runtime.context.user_id)
    if not context.profile:
        return NO_PROFILE_RECORDED, {"profile": None}

    return json.dumps(context.profile, ensure_ascii=False), {"profile": context.profile}


@tool(response_format="content_and_artifact")
async def update_user_profile(
    field: str, value: Any, runtime: ToolRuntime[UserAgentContext, Any]
) -> tuple[str, dict]:
    """Write one field of the user's profile.

    Pass the field's name exactly as it appears in the profile, and the new value. A
    field with nothing on file yet is written immediately. A field that already carries
    a value is an overwrite, and is staged for the user's confirmation instead — check
    the result to see which one happened, and tell the user accordingly.
    """

    if field not in UserProfile.model_fields:
        return f"'{field}' is not a profile field.", {"status": "invalid_field"}

    user_id = runtime.context.user_id
    profile = (await load_user_context(user_id)).profile or {}
    previous = profile.get(field)

    if _is_blank(previous):
        updated = await save_profile(user_id, {field: value})
        return (
            f"Saved {field} = {value!r}.",
            {"status": "written", "field": field, "profile": updated},
        )

    return (
        f"{field} is already {previous!r}; that change needs the user's confirmation.",
        {
            "status": "pending_approval",
            "field": field,
            "previous": previous,
            "value": value,
        },
    )
