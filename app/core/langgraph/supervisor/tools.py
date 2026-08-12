"""The supervisor's tools.

Six of them, and the shape of the list is what §2's translation rule produced.
For every pair of adjacent steps in the old graph, the question was: *if the
agent runs the first and skips the second, is the result wrong?* Where the answer
was yes and the two belonged to one operation, they became one tool body — which
is why there is no ``build_diff`` tool and no ``calc_macro`` tool here.

Three properties are enforced structurally rather than by prompt:

* **The profile gate is a precondition, not a tool.** Given ``check_profile()``
  as an option, some turns the model decides the profile looks complete and
  proceeds with ``activity_level = None``, producing a TDEE wrong by several
  hundred calories that looks authoritative. So it is checked on the first line
  of every tool that could produce a plan, and no such tool accepts ``profile``
  as a parameter — one that did would let the model fill in ``weight_kg=75`` for
  a user who never said it (§10).
* **``save_plan`` takes no plan argument.** The content comes from the draft
  store, so the numbers written to ``plan_versions`` are the numbers that were
  verified, not a version the model retyped (§4.2).
* **Subagents are called as tools, not handed control.** A handoff would end the
  supervisor's turn, and the confirm gate, the save and the final answer all live
  at supervisor level — nothing would be left to run them.
"""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph import drafts
from app.core.langgraph.agents import get_agent
from app.core.langgraph.agents.qa import EXHAUSTED_ANSWER, FAILURE_ANSWER
from app.core.langgraph.diff import build_diff
from app.core.langgraph.rendering import (
    render_plan,
    render_plan_context,
)
from app.core.langgraph.scoring import score, sort_issues
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.utils import message_text
from app.core.langgraph.versioning import describe_verification_reason, render_versions
from app.core.logging import logger
from app.schemas.graph import Issue, MissingFields, SavedVersion, ToolRefusal
from app.services.catalog import load_catalog
from app.services.profile import FIELD_LABELS, GOAL_LABELS, missing_fields, profile_hash
from app.services.rubrics import rubric_version
from app.services.versions import get_version, insert_version, version_index

_NO_HISTORY = (
    "There is no earlier version to go back to — the plan the user has is the only one saved."
)


@tool
async def planning_agent(
    runtime: ToolRuntime, mode: str = "build", changes: dict | None = None
) -> Command:
    """Build a training plan, or change the one the user already has.

    The profile is read from the database. It is never passed in — anything you
    would type here about the user is a guess, and the tool refuses rather than
    plan on a guess.

    Use ``mode="change"`` with ``changes`` when the user has a plan and asked to
    alter it: ``{"days": 5}`` or ``{"goal": "fat_loss"}`` are the two deltas that
    can be applied. Use ``mode="build"`` otherwise.

    The plan is verified before it comes back. What you receive is a handle plus
    a rendering — describe the plan from the rendering, and pass the handle to
    ``save_plan`` when the user wants it kept.

    Args:
        runtime: Tool runtime, read for the supervisor's state and config.
        mode: ``"build"`` or ``"change"``.
        changes: The delta to apply, for a change.

    Returns:
        A draft envelope, or a refusal naming what is missing.
    """
    state: SupervisorState = runtime.state
    profile = state.get("profile") or {}
    intent = "change_plan" if mode == "change" else "build_plan"

    refusal = _profile_precondition(profile, intent, state)
    if refusal is not None:
        return _refuse(runtime.tool_call_id, refusal, missing=refusal.get("fields"))

    if mode == "change" and not state.get("plan"):
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason="There is no saved plan to change yet. Build one first.",
            ),
        )

    result = await get_agent("planning").ainvoke(
        {
            "messages": [],
            "profile": profile,
            "goal": profile.get("goal", "general_health"),
            "preferences": profile.get("preferences", ""),
            "mode": "change" if mode == "change" else "build",
            "changes": changes or {},
            "base_plan": state.get("plan") if mode == "change" else None,
            "base_macros": state.get("macros") if mode == "change" else None,
            "template": None,
            "slots": [],
            "notes": [],
            "draft_id": None,
        },
        runtime.config,
    )

    draft_id = result.get("draft_id")
    if not draft_id:
        # The agent produced no handle, so it produced nothing the system will
        # save. Whatever it wrote in its own transcript is not a plan.
        reason = message_text(result["messages"][-1]) if result.get("messages") else ""
        logger.info("planning_agent_produced_no_draft", mode=mode)
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason=reason or "No plan could be produced for this profile.",
            ),
        )

    draft = drafts.read(draft_id)
    if draft is None:
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(status="refused", reason="The draft expired before it could be read."),
        )

    return _result(runtime.tool_call_id, drafts.envelope(draft))


@tool
async def review_agent(pasted: str, runtime: ToolRuntime) -> Command:
    """Assess a training plan the user pasted in.

    Read-only. This produces an assessment, never a plan that can be saved — a
    plan someone pasted to ask an opinion about must not replace the one they
    follow, and there is no handle in the result for ``save_plan`` to accept.

    Args:
        pasted: The plan text as the user wrote it. Copy it across verbatim;
            correcting spelling or expanding abbreviations destroys the evidence
            that a name was ambiguous.
        runtime: Tool runtime, read for the supervisor's state and config.

    Returns:
        The assessment, or a refusal naming what is missing.
    """
    state: SupervisorState = runtime.state
    profile = state.get("profile") or {}

    refusal = _profile_precondition(profile, "check", state)
    if refusal is not None:
        return _refuse(runtime.tool_call_id, refusal, missing=refusal.get("fields"))

    result = await get_agent("review").ainvoke(
        {
            "messages": [HumanMessage(content=pasted)],
            "catalog": load_catalog(),
            "profile": profile,
            "submitted_plan": None,
            "unresolved": [],
            "incomplete": [],
            "scored": False,
        },
        runtime.config,
    )

    report = message_text(result["messages"][-1]) if result.get("messages") else ""
    logger.info(
        "review_agent_finished",
        scored=bool(result.get("scored")),
        unresolved=len(result.get("unresolved") or []),
    )
    return _result(
        runtime.tool_call_id,
        {
            "status": "review",
            "scored": bool(result.get("scored")),
            "report": report or "The plan could not be assessed.",
        },
    )


@tool
async def qa_agent(question: str, runtime: ToolRuntime) -> Command:
    """Answer a training or nutrition question, including one about this user.

    Handles knowledge questions, questions about the plan the user already has,
    and what-if questions about their targets. It searches the knowledge base and
    can estimate hypothetical macros; it changes nothing.
    """
    state: SupervisorState = runtime.state

    try:
        result = await get_agent("qa").ainvoke(
            {
                "messages": [HumanMessage(content=question)],
                "plan_context": render_plan_context(state.get("plan"), state.get("macros")),
                "episodic_context": state.get("episodic_context") or "",
                "profile": state.get("profile") or {},
            },
            runtime.config,
        )
    except Exception as e:
        # Every model in the registry has already been tried by the agent's
        # fallback middleware. The turn still owes the user a sentence.
        logger.exception("qa_agent_failed", error=str(e))
        return _result(runtime.tool_call_id, {"status": "answered", "answer": FAILURE_ANSWER})

    # An empty last message means the agent stopped on its call limit before
    # writing anything. Nothing failed, so this is not the failure wording.
    answer = message_text(result["messages"][-1]) or EXHAUSTED_ANSWER
    return _result(runtime.tool_call_id, {"status": "answered", "answer": answer})


@tool
async def list_versions(runtime: ToolRuntime) -> Command:
    """List the plan versions this user has saved, newest first.

    Call this before ``restore_version`` when the user asks to go back to an
    earlier plan. The list is loaded fresh: a plan may have been saved in a
    different session, and the versions they are choosing between must be the
    current ones.

    Args:
        runtime: Tool runtime, read for the session owner.

    Returns:
        The version index, or a note saying there is no history.
    """
    user_id = _user_id(runtime)
    if user_id is None:
        return _result(runtime.tool_call_id, {"status": "no_history", "reason": _NO_HISTORY})

    index = await version_index(user_id)
    if len(index) <= 1:
        # One version is the plan they already have. There is nothing to go back
        # to, and saying so beats offering a list of one.
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
    was valid when it was saved may not be valid now — the user may have lost
    weight, or declared an injury that did not exist then. Saving it appends a
    new version rather than deleting the ones since, so the user can undo the
    undo.

    Args:
        version_id: The version to restore.
        runtime: Tool runtime, read for the supervisor's state and config.

    Returns:
        A draft envelope, or a refusal when the version is gone.
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

    if version.user_id != _user_id(runtime):
        # Not a 404 dressed up: an id belonging to someone else is not a version
        # this session may read, and saying so differently would confirm it
        # exists.
        logger.warning("restore_version_owner_mismatch", version_id=version_id)
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(status="refused", reason=f"There is no version '{version_id}'."),
        )

    plan = dict(version.plan)
    macros, issues, verdict = await score(plan, profile)
    note = _restore_note(
        version.label, describe_verification_reason(version.profile_hash, profile_hash(profile))
    )

    draft = drafts.mint(
        plan=plan,
        macros=macros,
        issues=[note, *issues],
        verdict=verdict,
        plan_rendered=render_plan(plan, macros.get("goal")),
        profile_hash=profile_hash(profile),
        rubric_version=rubric_version(),
        diff=build_diff(state.get("plan"), plan, state.get("macros"), macros),
        restored_from=version.id,
        parent_id=state.get("current_version_id"),
    )
    logger.info("version_restored_as_draft", version_id=version_id, draft_id=draft.draft_id)
    return _result(runtime.tool_call_id, drafts.envelope(draft))


@tool
async def save_plan(draft_id: str, runtime: ToolRuntime) -> Command:
    """Save a draft as the user's plan.

    Takes only the handle. The plan, the targets and the verdict are read from
    the draft, so what gets stored is what was verified — not a version rewritten
    on the way here. There is no parameter for the plan, deliberately.

    The user is asked before this runs. Do not call it on your own initiative
    after a build; call it when they say to keep the plan.

    Args:
        draft_id: The handle a planning or restore call returned.
        runtime: Tool runtime, read for the supervisor's state and config.

    Returns:
        The saved version's id and label, or a refusal.
    """
    state: SupervisorState = runtime.state
    draft = drafts.read(draft_id)

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
        # Refused here and not only when the answer is composed. A failing plan
        # that reaches the store is a failing plan the user trains.
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

    user_id = _user_id(runtime)
    update: dict[str, Any] = {"plan": draft.plan, "macros": draft.macros}

    if user_id is None:
        # An anonymous session has no user to own the row. The plan still becomes
        # what this conversation holds; it simply does not outlive it.
        logger.info("snapshot_skipped_anonymous_session")
        drafts.expire(draft_id)
        return _result(
            runtime.tool_call_id,
            {"status": "saved", "version_id": "", "label": "unsaved (not signed in)"},
            update,
        )

    ref = await insert_version(
        user_id=user_id,
        plan=draft.plan,
        macros=draft.macros,
        profile_hash=draft.profile_hash,
        rubric_version=draft.rubric_version,
        # Append-only history: the version this one supersedes is recorded
        # rather than replaced, so an undo has something to come back to.
        parent_id=draft.parent_id or state.get("current_version_id"),
        # A restore is an append, not a rewind. Recording where the content came
        # from is what lets the user undo the undo — and they will.
        restored_from=draft.restored_from,
        # The edge the episodic layer reads: this conversation produced this plan.
        session_id=_session_id(runtime),
    )
    update["current_version_id"] = ref["version_id"]
    drafts.expire(draft_id)

    logger.info("plan_saved", version_id=ref["version_id"], label=ref["label"])
    return _result(
        runtime.tool_call_id,
        SavedVersion(status="saved", version_id=ref["version_id"], label=ref["label"]),
        update,
    )


tools = [planning_agent, review_agent, qa_agent, list_versions, restore_version, save_plan]

# The one tool that writes. Named here so the check that no subagent can reach it
# is a lookup rather than a reading of six tool bodies.
WRITE_TOOLS = frozenset({"save_plan"})


def _profile_precondition(
    profile: dict, intent: str, state: SupervisorState
) -> MissingFields | ToolRefusal | None:
    """Refuse when the profile cannot support this operation.

    Two checks, both of which used to be root nodes with an edge into the only
    branch point. ``missing_fields`` is a constant lookup, not a model's judgment
    about whether it has enough information; the goal conflict stops a turn from
    silently planning against a goal the user may have moved off.

    Args:
        profile: The merged profile.
        intent: ``build_plan``, ``change_plan`` or ``check``.
        state: Current supervisor state, read for a pending goal conflict.

    Returns:
        The refusal to return, or ``None`` when the tool may proceed.
    """
    missing = missing_fields(profile, intent)
    if missing:
        logger.info("tool_precondition_missing_fields", intent=intent, missing=missing)
        return MissingFields(status="missing_fields", fields=missing)

    conflict = state.get("goal_conflict")
    if conflict and intent in {"build_plan", "change_plan"}:
        stored = GOAL_LABELS.get(conflict["stored"], conflict["stored"])
        implied = GOAL_LABELS.get(conflict["implied"], conflict["implied"])
        return ToolRefusal(
            status="refused",
            reason=(
                f"Their profile has {stored} as the goal, but this message reads more like "
                f"{implied}. It moves the calorie target in opposite directions, so ask which "
                "one to plan for before building anything."
            ),
        )

    return None


def _restore_note(label: str, verification_reason: str) -> Issue:
    """Record which version is being restored and whether its checks still hold.

    Carried as an ``info`` issue so it travels with every other finding, and the
    answer cannot describe a restore without also saying what was re-checked.

    Args:
        label: The version being restored, e.g. ``"v1"``.
        verification_reason: Whether the profile has moved since it was saved.

    Returns:
        The note.
    """
    return Issue(
        source="volume",
        severity="info",
        location=f"Restoring {label}",
        message=verification_reason,
        suggestion=None,
        rubric_ref="versions.restore",
    )


def _result(
    tool_call_id: str, payload: dict[str, Any], update: dict[str, Any] | None = None
) -> Command:
    """Return a tool result, optionally with a state update alongside it.

    Args:
        tool_call_id: The call being answered.
        payload: What the model sees.
        update: State the tool changed, e.g. the plan a save made current.

    Returns:
        The command carrying both.
    """
    body = dict(payload)
    issues = body.get("issues")
    if isinstance(issues, list):
        body["issues"] = [
            {
                "severity": issue["severity"],
                "location": issue["location"],
                "message": issue["message"],
                "rubric_ref": issue["rubric_ref"],
            }
            for issue in sort_issues(issues)
        ]

    return Command(
        update={
            **(update or {}),
            "messages": [
                ToolMessage(
                    content=json.dumps(body, ensure_ascii=False, default=str),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


def _refuse(
    tool_call_id: str, refusal: MissingFields | ToolRefusal, missing: list[str] | None = None
) -> Command:
    """Return a refusal the supervisor can act on.

    Returned rather than raised. The supervisor's next move is to ask the user
    for what is missing, and a refusal it can read is what makes calling the tool
    anyway achieve nothing but a list of what to ask for.

    Args:
        tool_call_id: The call being answered.
        refusal: The refusal envelope.
        missing: Fields to record in state, so the prompt can name them next
            call without the model having to remember them.

    Returns:
        The command carrying the refusal.
    """
    body: dict[str, Any] = dict(refusal)
    if missing:
        # Phrased as questions, not column names. The supervisor asks for all of
        # them in one message; trickling them out one per turn is how a user ends
        # up answering a form.
        body["ask_for"] = [FIELD_LABELS.get(field, field) for field in missing]

    return Command(
        update={
            **({"missing_fields": missing} if missing else {}),
            "messages": [
                ToolMessage(
                    content=json.dumps(body, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        }
    )


def _user_id(runtime: ToolRuntime) -> int | None:
    """Read the session owner from the runnable config.

    Args:
        runtime: The tool runtime for this call.

    Returns:
        The user id, or ``None`` for an anonymous session.
    """
    user_id = ((runtime.config or {}).get("metadata") or {}).get("user_id")
    return int(user_id) if user_id else None


def _session_id(runtime: ToolRuntime) -> str | None:
    """Read the session id the checkpointer is keyed on.

    Args:
        runtime: The tool runtime for this call.

    Returns:
        The thread id, or ``None`` when there is none.
    """
    return ((runtime.config or {}).get("configurable") or {}).get("thread_id")


__all__ = [
    "WRITE_TOOLS",
    "list_versions",
    "planning_agent",
    "qa_agent",
    "restore_version",
    "review_agent",
    "save_plan",
    "tools",
]
