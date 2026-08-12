"""Planning tool and helpers for assembling and committing a draft."""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.agents.planning.state import PlanningState
from app.core.langgraph.plans.diff import build_diff
from app.core.langgraph.plans.rendering import render_plan
from app.core.langgraph.runtime import draft_store as drafts
from app.core.langgraph.verification.scoring import score
from app.core.logging import logger
from app.schemas.graph import Issue
from app.services.catalog import load_catalog
from app.services.profile import profile_hash
from app.services.rubrics import rubric_version
from app.services.templates import iter_slots


@tool
async def commit_draft(runtime: ToolRuntime, choices: list[dict] | None = None) -> Command:
    """Assemble the chosen exercises into a plan, verify it, and hold it as a draft.

    Computes nutrition targets, runs every rubric check, and stores the result
    under a handle. Nothing else produces a plan the system will save.

    A slot you do not name keeps the exercise it already has in change mode, and
    otherwise takes the first candidate — so a partial choice list is a valid
    call, not an error.
    """
    state: PlanningState = runtime.state
    template = state.get("template")
    slots = state.get("slots") or []
    if template is None or not slots:
        return _tool_error(
            runtime.tool_call_id,
            "There are no slots to commit. Call get_template_slots first.",
        )
    catalog = load_catalog()
    filled, rejected = _apply_choices(slots, choices or [])
    plan = _assemble(template, filled, catalog)
    _validate(plan, template, catalog)
    profile = state["profile"]
    macros, issues, verdict = await score(plan, profile)
    all_issues = _as_issues(state.get("notes") or []) + issues
    base_plan = state.get("base_plan")
    draft = drafts.mint(
        plan=plan,
        macros=macros,
        issues=all_issues,
        verdict=verdict,
        plan_rendered=render_plan(plan, macros.get("goal")),
        profile_hash=profile_hash(profile),
        rubric_version=rubric_version(),
        diff=(
            build_diff(base_plan, plan, state.get("base_macros"), macros)
            if state.get("mode") == "change" and base_plan
            else None
        ),
    )
    logger.info(
        "planning_draft_committed",
        draft_id=draft.draft_id,
        mode=state.get("mode"),
        verdict=verdict,
        choices=len(choices or []),
        rejected=rejected,
    )
    return Command(
        update={
            "draft_id": draft.draft_id,
            "messages": [
                ToolMessage(
                    content=_render_commit_result(draft),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


def _apply_choices(slots: list[dict], choices: list[dict]) -> tuple[list[dict], int]:
    """Resolve one exercise per slot from the model's choices."""
    chosen = {
        choice.get("slot_id"): choice.get("exercise_id")
        for choice in choices
        if isinstance(choice, dict)
    }
    filled: list[dict] = []
    used: set[str] = set()
    rejected = 0
    for slot in slots:
        allowed = {candidate["exercise_id"] for candidate in slot["candidates"]}
        proposed = chosen.get(slot["slot_id"])
        if proposed in allowed:
            exercise_id = proposed
        else:
            if proposed is not None:
                rejected += 1
                logger.warning(
                    "planning_choice_outside_candidate_list",
                    slot_id=slot["slot_id"],
                    proposed=proposed,
                )
            exercise_id = slot.get("current_exercise_id") or next(
                (
                    candidate["exercise_id"]
                    for candidate in slot["candidates"]
                    if candidate["exercise_id"] not in used
                ),
                slot["candidates"][0]["exercise_id"],
            )
        used.add(exercise_id)
        filled.append({**slot, "exercise_id": exercise_id})
    return filled, rejected


def _assemble(template: dict, slots: list[dict], catalog: dict[str, dict]) -> dict[str, Any]:
    """Build the plan JSON from filled slots."""
    by_day: dict[str, list[dict]] = {}
    for slot in slots:
        by_day.setdefault(slot["day_name"], []).append(
            {
                "slot_id": slot["slot_id"],
                "exercise_id": slot["exercise_id"],
                "name": catalog[slot["exercise_id"]]["name"],
                "sets": slot["sets"],
                "reps": slot["reps"],
                "rir": slot["rir"],
            }
        )
    return {
        "template_id": template["template_id"],
        "days": [
            {"name": day["name"], "exercises": by_day[day["name"]]}
            for day in template["days"]
            if day["name"] in by_day
        ],
    }


def _validate(plan: dict, template: dict, catalog: dict) -> None:
    """Check an assembled plan against its template and the catalog."""
    slots_by_id = {slot["slot_id"]: slot for slot in iter_slots(template)}
    for day in plan["days"]:
        for exercise in day["exercises"]:
            if exercise["exercise_id"] not in catalog:
                raise ValueError(
                    f"assembled plan references unknown exercise "
                    f"'{exercise['exercise_id']}' in '{day['name']}'"
                )
            slot = slots_by_id.get(exercise["slot_id"])
            if slot is None:
                raise ValueError(f"assembled plan has slot '{exercise['slot_id']}' not in template")
            if (exercise["sets"], exercise["reps"], exercise["rir"]) != (
                slot["sets"],
                slot["reps"],
                slot["rir"],
            ):
                raise ValueError(
                    f"slot '{slot['slot_id']}' prescription was modified: "
                    f"{exercise['sets']}x{exercise['reps']}@{exercise['rir']} != "
                    f"{slot['sets']}x{slot['reps']}@{slot['rir']}"
                )


def _as_issues(notes: list[dict[str, Any]]) -> list[Issue]:
    """Re-type notes read back out of state."""
    return [Issue(**note) for note in notes]


def _render_commit_result(draft: drafts.Draft) -> str:
    """Render what committing produced, for the model to act on."""
    return json.dumps(
        {
            "draft_id": draft.draft_id,
            "verdict": draft.verdict,
            "plan_rendered": draft.plan_rendered,
            "macros": draft.macros,
            "issues": [
                {
                    "severity": issue["severity"],
                    "location": issue["location"],
                    "message": issue["message"],
                    "rubric_ref": issue["rubric_ref"],
                }
                for issue in draft.issues
            ],
        },
        ensure_ascii=False,
    )


def _tool_error(tool_call_id: str, message: str) -> Command:
    """Return a tool failure the model can recover from."""
    return Command(
        update={
            "messages": [ToolMessage(content=message, tool_call_id=tool_call_id, status="error")]
        }
    )


__all__ = ["_apply_choices", "_assemble", "_validate", "commit_draft"]
