"""Supervisor tool for persisting an approved draft."""

from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.runtime import draft_store
from app.core.langgraph.runtime.context import get_session_id, get_user_id
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.supervisor.tools.responses import _refuse, _result
from app.core.logging import logger
from app.schemas.graph import SavedVersion, ToolRefusal
from app.services.versions import insert_version


@tool
async def save_plan(draft_id: str, runtime: ToolRuntime) -> Command:
    """Save a draft as the user's plan.

    Takes only the handle. The plan, the targets and the verdict are read from
    the draft, so what gets stored is what was verified — not a version rewritten
    on the way here. There is no parameter for the plan, deliberately.

    The user is asked before this runs. Do not call it on your own initiative
    after a build; call it when they say to keep the plan.
    """
    state: SupervisorState = runtime.state
    draft = draft_store.read(draft_id)
    if draft is None:
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason=(
                    "That draft has expired. Build the plan again — a draft this old was "
                    "checked against a profile that may have changed since."
                ),
            ),
        )
    if draft.verdict == "fail":
        blocking = [issue for issue in draft.issues if issue["severity"] == "block"]
        logger.info("save_refused_failing_draft", draft_id=draft_id, blocking=len(blocking))
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason=(
                    "This plan did not pass its checks, so it cannot be saved: "
                    + "; ".join(issue["message"] for issue in blocking)
                ),
            ),
        )
    user_id = get_user_id(runtime.config)
    update: dict[str, Any] = {"plan": draft.plan, "macros": draft.macros}
    if user_id is None:
        logger.info("snapshot_skipped_anonymous_session")
        draft_store.expire(draft_id)
        return _result(
            runtime.tool_call_id,
            {"status": "saved", "version_id": "", "label": "unsaved (not signed in)"},
            update,
        )
    reference = await insert_version(
        user_id=user_id,
        plan=draft.plan,
        macros=draft.macros,
        profile_hash=draft.profile_hash,
        rubric_version=draft.rubric_version,
        parent_id=draft.parent_id or state.get("current_version_id"),
        restored_from=draft.restored_from,
        session_id=get_session_id(runtime.config),
    )
    update["current_version_id"] = reference["version_id"]
    draft_store.expire(draft_id)
    logger.info("plan_saved", version_id=reference["version_id"], label=reference["label"])
    return _result(
        runtime.tool_call_id,
        SavedVersion(status="saved", version_id=reference["version_id"], label=reference["label"]),
        update,
    )


__all__ = ["save_plan"]
