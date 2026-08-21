"""Supervisor tools for listing and restoring plan versions."""

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.plans.diff import build_diff
from app.core.langgraph.plans.rendering import render_plan
from app.core.langgraph.plans.versioning import describe_verification_reason, render_versions
from app.core.langgraph.runtime import draft_store as drafts
from app.core.langgraph.runtime.context import get_user_id
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.supervisor.tools.responses import _refuse, _result
from app.core.langgraph.verification.scoring import score
from app.core.logging import logger
from app.schemas.graph import Issue, ToolRefusal
from app.services.profile import profile_hash
from app.services.rubrics import rubric_version
from app.services.versions import get_version, version_index

_NO_HISTORY = (
    "There is no earlier version to go back to — the plan the user has is the only one saved."
)


@tool
async def list_versions(runtime: ToolRuntime) -> Command:
    """List the plan versions this user has saved, newest first.

    Call this before ``restore_version`` when the user asks to go back to an
    earlier plan. The list is loaded fresh: a plan may have been saved in a
    different session, and the versions they are choosing between must be the
    current ones.
    """
    user_id = get_user_id(runtime.config)
    if user_id is None:
        return _result(runtime.tool_call_id, {"status": "no_history", "reason": _NO_HISTORY})
    index = await version_index(user_id)
    if len(index) <= 1:
        return _result(runtime.tool_call_id, {"status": "no_history", "reason": _NO_HISTORY})
    return _result(
        runtime.tool_call_id,
        {
            "status": "versions",
            "current": index[0]["version_id"],
            "rendered": render_versions(index),
        },
    )


@tool
async def restore_version(version_id: str, runtime: ToolRuntime) -> Command:
    """Bring back a saved version of the plan, re-checked against the profile now.

    Pass a ``version_id`` from ``list_versions``. Never invent one — an id that
    is not in that list does not exist.

    A restore is not a rewind: the old plan is re-verified, because a plan that
    was valid when it was saved may not be valid now. Saving it appends a new
    version rather than deleting the ones since.
    """
    state: SupervisorState = runtime.state
    profile = state.get("profile") or {}
    version = await get_version(version_id)
    if version is None:
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason=(
                    f"There is no version '{version_id}'. Call list_versions and use an id "
                    "from that list."
                ),
            ),
        )
    if version.user_id != get_user_id(runtime.config):
        logger.warning("restore_version_owner_mismatch", version_id=version_id)
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(status="refused", reason=f"There is no version '{version_id}'."),
        )
    plan = dict(version.plan)
    macros, issues, verdict = await score(plan, profile)
    hash_profile = profile_hash
    note = _restore_note(
        version.label, describe_verification_reason(version.profile_hash, hash_profile(profile))
    )
    draft = drafts.mint(
        plan=plan,
        macros=macros,
        issues=[note, *issues],
        verdict=verdict,
        plan_rendered=render_plan(plan, macros.get("goal")),
        profile_hash=hash_profile(profile),
        rubric_version=rubric_version(),
        diff=build_diff(state.get("plan"), plan, state.get("macros"), macros),
        restored_from=version.id,
        parent_id=state.get("current_version_id"),
    )
    logger.info("version_restored_as_draft", version_id=version_id, draft_id=draft.draft_id)
    return _result(runtime.tool_call_id, drafts.envelope(draft))


def _restore_note(label: str, verification_reason: str) -> Issue:
    """Record which version is being restored and whether its checks still hold."""
    return Issue(
        source="volume",
        severity="info",
        location=f"Restoring {label}",
        message=verification_reason,
        suggestion=None,
        rubric_ref="versions.restore",
    )


__all__ = ["_NO_HISTORY", "_restore_note", "list_versions", "restore_version"]
