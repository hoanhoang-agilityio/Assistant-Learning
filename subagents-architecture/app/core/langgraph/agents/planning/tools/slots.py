"""Planning tools and helpers for preparing exercise slots."""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.agents.planning.issues import make_planning_issue as _issue
from app.core.langgraph.agents.planning.patch import patch_plan
from app.core.langgraph.agents.planning.state import PlanningState
from app.schemas.graph import Issue
from app.services.catalog import (
    candidates_for_slot,
    forbidden_joint_actions,
    forbidden_loaded_positions,
    load_catalog,
)
from app.services.rubrics import contraindications
from app.services.templates import get_template, iter_slots, query_templates

_MAX_CANDIDATES = 8
_SPLIT_SHAPE_TERMS = frozenset(
    {
        "upper body",
        "upper-body",
        "lower body",
        "lower-body",
        "full body",
        "full-body",
        "push pull",
        "push/pull",
        "push-pull",
        "bro split",
        "arnold split",
        "body part split",
    }
)


@tool
async def get_template_slots(runtime: ToolRuntime) -> Command:
    """Get the programme skeleton and the legal exercise options for each slot.

    Call this first. It returns one slot per exercise the programme prescribes,
    each with the exercises that are safe and available for this user. In change
    mode each slot also carries the exercise the current plan already uses.
    """
    state: PlanningState = runtime.state
    profile = state["profile"]
    catalog = load_catalog()
    if state.get("mode") == "change":
        template, slots, notes = _change_slots(
            state.get("base_plan") or {}, state.get("changes") or {}, profile, catalog
        )
    else:
        template, slots, notes = _build_slots(
            profile, state.get("goal") or "general_health", state.get("preferences") or "", catalog
        )
    if template is None:
        return Command(
            update={
                "template": None,
                "slots": [],
                "notes": notes,
                "messages": [
                    ToolMessage(
                        content=_render_refusal(notes),
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ],
            }
        )
    return Command(
        update={
            "template": template,
            "slots": slots,
            "notes": notes,
            "messages": [
                ToolMessage(
                    content=_render_slots(slots, notes),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
def get_exercise_candidates(
    slot_id: str, runtime: ToolRuntime, exclude_ids: list[str] | None = None
) -> str:
    """List the exercises that may fill one slot, optionally excluding some.

    Every id returned is already filtered against this user's injuries and
    equipment. Ask for a slot again with ``exclude_ids`` when a first choice
    turned out to be wrong.
    """
    state: PlanningState = runtime.state
    slot = next((entry for entry in state.get("slots") or [] if entry["slot_id"] == slot_id), None)
    if slot is None:
        return f"No slot '{slot_id}'. Call get_template_slots to see the slots that exist."
    excluded = set(exclude_ids or [])
    remaining = [
        candidate for candidate in slot["candidates"] if candidate["exercise_id"] not in excluded
    ]
    if not remaining:
        return (
            f"Every legal option for '{slot_id}' is excluded. Keep the one already chosen, "
            "or exclude fewer."
        )
    return json.dumps(
        {"slot_id": slot_id, "pattern": slot["pattern"], "candidates": remaining},
        ensure_ascii=False,
    )


def _build_slots(
    profile: dict[str, Any], goal: str, preferences: str, catalog: dict[str, dict]
) -> tuple[dict | None, list[dict], list[Issue]]:
    """Pick the programme skeleton and attach each slot's legal options."""
    matches = query_templates(
        days_per_week=profile.get("days_per_week"), goal=goal, level=profile.get("level", 1)
    )
    if not matches:
        return (
            None,
            [],
            [
                _issue(
                    "block",
                    "Programme",
                    f"No programme template matches {profile.get('days_per_week')} sessions a "
                    f"week for a {goal} goal at your experience level. Try a different number "
                    "of sessions.",
                    "templates.no_match",
                )
            ],
        )
    template = matches[0]
    notes = _split_preference_notes(preferences, template, len(matches))
    slots, dropped = _attach_candidates(iter_slots(template), profile, catalog)
    notes.extend(dropped)
    if not slots:
        return None, [], notes
    return template, slots, notes


def _change_slots(
    base_plan: dict[str, Any],
    changes: dict[str, Any],
    profile: dict[str, Any],
    catalog: dict[str, dict],
) -> tuple[dict | None, list[dict], list[Issue]]:
    """Apply the requested change, then expose the result as slots."""
    patched, notes = patch_plan(base_plan, changes, profile, catalog)
    if patched is None:
        return None, [], notes
    template = get_template(patched.get("template_id") or "")
    if template is None:
        return (
            None,
            [],
            [
                *notes,
                _issue(
                    "block",
                    "Programme",
                    "The programme this plan was built from is no longer in the library, "
                    "so it cannot be changed. Building a new plan is the way forward.",
                    "templates.missing",
                ),
            ],
        )
    current = {
        exercise["slot_id"]: exercise["exercise_id"]
        for day in patched.get("days") or []
        for exercise in day.get("exercises") or []
    }
    slots, dropped = _attach_candidates(iter_slots(template), profile, catalog, current)
    if not slots:
        return None, [], [*notes, *dropped]
    return template, slots, [*notes, *dropped]


def _attach_candidates(
    slots: list[dict[str, Any]],
    profile: dict[str, Any],
    catalog: dict[str, dict],
    current: dict[str, str] | None = None,
) -> tuple[list[dict], list[Issue]]:
    """Attach the legal exercise options to every slot."""
    rubric = contraindications()
    forbidden_actions = forbidden_joint_actions(profile, rubric)
    forbidden_positions = forbidden_loaded_positions(profile, rubric)
    fillable: list[dict] = []
    issues: list[Issue] = []
    for slot in slots:
        candidates = candidates_for_slot(
            slot, profile, catalog, forbidden_actions, forbidden_positions
        )
        if not candidates:
            issues.append(_dropped_slot_issue(slot, profile))
            continue
        entry = {
            **slot,
            "candidates": [
                {
                    "exercise_id": candidate["exercise_id"],
                    "name": candidate["name"],
                    "equipment": candidate["equipment"],
                }
                for candidate in candidates[:_MAX_CANDIDATES]
            ],
        }
        if current and slot["slot_id"] in current:
            entry["current_exercise_id"] = current[slot["slot_id"]]
        fillable.append(entry)
    return fillable, issues


def _split_preference_notes(preferences: str, template: dict, match_count: int) -> list[Issue]:
    """Say out loud when a requested split could not be honoured."""
    lowered = preferences.lower()
    if not any(term in lowered for term in _SPLIT_SHAPE_TERMS):
        return []
    days = " / ".join(day["name"] for day in template["days"])
    only = " the only programme" if match_count == 1 else " the closest programme"
    return [
        _issue(
            "info",
            "Programme",
            f'You asked for a particular split ("{preferences}"). The split comes from '
            f"the programme library, which is matched on your days a week, goal and "
            f"experience — not on this preference — and {template['name']} is{only} "
            f"that matches. Your sessions are therefore {days}. The preference was still "
            "used when choosing the exercises within each session.",
            "templates.split_preference_unmatched",
        )
    ]


def _dropped_slot_issue(slot: dict, profile: dict) -> Issue:
    """Explain why a slot could not be filled."""
    injuries = profile.get("injuries") or []
    if injuries:
        message = (
            f"No {slot['pattern'].replace('_', ' ')} exercise is safe given your declared "
            "injury, so this slot was left out of the plan."
        )
        source = "injury"
        rubric_ref = f"contraindications.{injuries[0]}"
    else:
        message = (
            f"No {slot['pattern'].replace('_', ' ')} exercise matches your available "
            "equipment and experience level, so this slot was left out."
        )
        source = "volume"
        rubric_ref = "catalog.no_candidates"
    return Issue(
        source=source,
        severity="warn",
        location=f"{slot['day_name']} / {slot['pattern'].replace('_', ' ')}",
        message=message,
        suggestion=None,
        rubric_ref=rubric_ref,
    )


def _render_slots(slots: list[dict], notes: list[Issue]) -> str:
    """Render the slot list as the tool's result."""
    return json.dumps(
        {
            "slots": [
                {
                    "slot_id": slot["slot_id"],
                    "day": slot["day_name"],
                    "pattern": slot["pattern"],
                    "sets": slot["sets"],
                    "reps": slot["reps"],
                    **(
                        {"current_exercise_id": slot["current_exercise_id"]}
                        if "current_exercise_id" in slot
                        else {}
                    ),
                    "candidates": slot["candidates"],
                }
                for slot in slots
            ],
            "notes": [note["message"] for note in notes],
        },
        ensure_ascii=False,
    )


def _render_refusal(notes: list[Issue]) -> str:
    """Render why no plan can be produced at all."""
    if not notes:
        return "No plan can be produced for this profile, and no reason was recorded."
    return "No plan can be produced. " + " ".join(note["message"] for note in notes)


__all__ = [
    "_attach_candidates",
    "_build_slots",
    "_change_slots",
    "get_exercise_candidates",
    "get_template_slots",
]
