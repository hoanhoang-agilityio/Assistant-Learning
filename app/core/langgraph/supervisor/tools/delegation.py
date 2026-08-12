"""Supervisor tools that delegate work to specialist agents."""

from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.agents.qa import EXHAUSTED_ANSWER, FAILURE_ANSWER
from app.core.langgraph.agents.registry import get_agent
from app.core.langgraph.plans.rendering import render_plan_context
from app.core.langgraph.runtime import draft_store
from app.core.langgraph.runtime.messages import message_text
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.supervisor.tools.responses import _refuse, _result
from app.core.logging import logger
from app.schemas.graph import MissingFields, ToolRefusal
from app.services.catalog import load_catalog
from app.services.profile import GOAL_LABELS, missing_fields


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
        reason = message_text(result["messages"][-1]) if result.get("messages") else ""
        logger.info("planning_agent_produced_no_draft", mode=mode)
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(
                status="refused",
                reason=reason or "No plan could be produced for this profile.",
            ),
        )
    draft = draft_store.read(draft_id)
    if draft is None:
        return _refuse(
            runtime.tool_call_id,
            ToolRefusal(status="refused", reason="The draft expired before it could be read."),
        )
    return _result(runtime.tool_call_id, draft_store.envelope(draft))


@tool
async def review_agent(pasted: str, runtime: ToolRuntime) -> Command:
    """Assess a training plan the user pasted in.

    Read-only. This produces an assessment, never a plan that can be saved — a
    plan someone pasted to ask an opinion about must not replace the one they
    follow, and there is no handle in the result for ``save_plan`` to accept.
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
    except Exception as error:
        logger.exception("qa_agent_failed", error=str(error))
        return _result(runtime.tool_call_id, {"status": "answered", "answer": FAILURE_ANSWER})
    answer = message_text(result["messages"][-1]) or EXHAUSTED_ANSWER
    return _result(runtime.tool_call_id, {"status": "answered", "answer": answer})


def _profile_precondition(
    profile: dict, intent: str, state: SupervisorState
) -> MissingFields | ToolRefusal | None:
    """Refuse when the profile cannot support this operation."""
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


__all__ = ["_profile_precondition", "planning_agent", "qa_agent", "review_agent"]
