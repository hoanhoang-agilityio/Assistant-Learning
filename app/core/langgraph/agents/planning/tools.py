"""Tools of the planning agent.

Three tools, and the boundaries between them are the whole design
(``docs/supervisor-architecture.md`` §5.2). The question that produced this list
is not "what is a nice granularity" but: *if the agent runs the first step and
skips the second, is the result wrong?*

* ``get_template_slots`` bundles template selection and candidate filtering. A
  slot list without candidates is useless, and filtering is not a decision.
* ``get_exercise_candidates`` is the one place the model chooses. Injury
  filtering happens inside it, never in the prompt — a rule stated in a prompt
  is a rule a model may weigh against something else.
* ``commit_draft`` bundles assembly, macros, verification and the draft-store
  write. Those four cannot be separated: a tool that returned a plan without
  having verified it is a tool that will eventually be called on its own.

``commit_draft`` is the **only** path that mints a ``draft_id``, and the
supervisor only accepts envelopes that carry one. An agent that assembles a plan
by itself and reports it has produced nothing the system will save.
"""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph import drafts
from app.core.langgraph.agents.planning.patch import patch_plan
from app.core.langgraph.agents.planning.state import PlanningState
from app.core.langgraph.diff import build_diff
from app.core.langgraph.rendering import render_plan
from app.core.langgraph.scoring import score
from app.core.logging import logger
from app.schemas.graph import Issue
from app.services.catalog import (
    candidates_for_slot,
    forbidden_joint_actions,
    forbidden_loaded_positions,
    load_catalog,
)
from app.services.profile import profile_hash
from app.services.rubrics import contraindications, rubric_version
from app.services.templates import get_template, iter_slots, query_templates

# Candidates shown per slot. The full legal list for a compound slot can run to
# thirty entries, and a model asked to pick one from thirty spends context it
# needs for the rest of the week. Truncation is safe because the list is already
# ordered by how well the exercise fits the slot.
_MAX_CANDIDATES = 8

# Words that describe the *shape* of a programme rather than a movement someone
# likes or avoids. A preference naming one of these is asking for a split, and
# the split is the one thing `preferences` cannot influence: it comes from the
# template library, matched on days, goal and level alone.
#
# A list of terms rather than a model call, because this only decides whether to
# add one explanatory line. It under-fires on phrasings nobody listed here, and
# that failure is silence — the same silence as before — rather than a wrong
# claim about what the plan does.
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

    Args:
        runtime: Tool runtime, read for the agent's state and this call's id.

    Returns:
        A command writing the template, the slots and any setup notes into
        state, and reporting the slot list back to the model.
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
        # A conflicting constraint, already explained in `notes`. There is no
        # plan to make, and saying so is the whole result.
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
    turned out to be wrong — for instance after a verification finding named it.

    Args:
        slot_id: The slot to list options for.
        runtime: Tool runtime, read for the agent's state.
        exclude_ids: Exercise ids to leave out, e.g. ones already used this week.

    Returns:
        The remaining candidates as JSON, or a message naming the fault when the
        slot is unknown or nothing is left.
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


@tool
async def commit_draft(runtime: ToolRuntime, choices: list[dict] | None = None) -> Command:
    """Assemble the chosen exercises into a plan, verify it, and hold it as a draft.

    Computes nutrition targets, runs every rubric check, and stores the result
    under a handle. Nothing else produces a plan the system will save.

    A slot you do not name keeps the exercise it already has in change mode, and
    otherwise takes the first candidate — so a partial choice list is a valid
    call, not an error.

    Args:
        runtime: Tool runtime, read for the agent's state and this call's id.
        choices: ``[{"slot_id": ..., "exercise_id": ...}]``. Every id must come
            from that slot's candidate list; anything else is rejected and the
            slot falls back.

    Returns:
        A command writing the draft handle into state and reporting the verdict,
        the targets and the findings back to the model.
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
        # `None` for a build: there is nothing to compare against, and an empty
        # diff would render a confirm question about no change at all.
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


tools = [get_template_slots, get_exercise_candidates, commit_draft]


# ----------------------------------------------------------------------
# Slot preparation
# ----------------------------------------------------------------------


def _build_slots(
    profile: dict[str, Any], goal: str, preferences: str, catalog: dict[str, dict]
) -> tuple[dict | None, list[dict], list[Issue]]:
    """Pick the programme skeleton and attach each slot's legal options.

    Takes the most popular matching template rather than asking a model: days
    per week, goal and level are exact criteria, so there is nothing to judge.

    A slot with no legal candidate is dropped and reported, not failed. That
    case is reachable and correct — shoulder impingement rules out overhead
    abduction, and every vertical press involves it — so the honest outcome is a
    plan without that slot plus a line saying why.

    Args:
        profile: The user's profile.
        goal: The goal to plan for.
        preferences: The user's stated preferences, free text.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(template, slots, notes)``. ``template`` is ``None`` when no programme
        fits or nothing at all can be filled.
    """
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
    """Apply the requested change, then expose the result as slots.

    The change itself is deterministic — ``patch_plan`` decides which template
    the plan moves onto and which exercises carry over — and that is deliberate:
    modification must not become regeneration. Rebuilding from scratch would
    quietly drop every exercise the user has been happy with for six weeks.

    What the model gets afterwards is the same slot list a build gets, with the
    carried exercise marked. So it can commit the patch as it stands, which is
    the normal path, or vary the slots a verification finding names.

    Args:
        base_plan: The plan the user already approved.
        changes: The delta to apply.
        profile: The user's profile.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(template, slots, notes)``. ``template`` is ``None`` when the change
        cannot be applied at all.
    """
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
    """Attach the legal exercise options to every slot.

    Every legal candidate is attached, with no exclusion for exercises used by
    an earlier slot. Avoiding repeats across the week is the model's job, and
    doing it here would be wrong twice over: it reserves an exercise the model
    has not chosen yet, and it shrinks later slots' lists on the strength of that
    guess — which can empty a slot that had legal options.

    Args:
        slots: Template slots.
        profile: The user's profile, for the injury and equipment filters.
        catalog: Exercise metadata keyed by id.
        current: ``slot_id -> exercise_id`` already in the plan, for a change.

    Returns:
        ``(fillable_slots, issues)``.
    """
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


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------


def _apply_choices(slots: list[dict], choices: list[dict]) -> tuple[list[dict], int]:
    """Resolve one exercise per slot from the model's choices.

    A choice outside the slot's candidate list is rejected and logged, never
    applied. That check is what makes it structurally impossible for a
    hallucinated or contraindicated exercise to enter a plan, and it is why the
    injury filter lives in a tool body rather than in a prompt.

    Args:
        slots: Slots carrying their candidate lists.
        choices: What the model chose.

    Returns:
        ``(slots_with_exercise_id, rejected_count)``.
    """
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
            # Keep what the plan already had in change mode; otherwise take the
            # first candidate not already used this week, so the deterministic
            # path still varies the plan. If every candidate is taken, repeat
            # rather than leave the slot empty.
            exercise_id = slot.get("current_exercise_id") or next(
                (c["exercise_id"] for c in slot["candidates"] if c["exercise_id"] not in used),
                slot["candidates"][0]["exercise_id"],
            )

        used.add(exercise_id)
        filled.append({**slot, "exercise_id": exercise_id})

    return filled, rejected


def _assemble(template: dict, slots: list[dict], catalog: dict[str, dict]) -> dict[str, Any]:
    """Build the plan JSON from filled slots.

    Args:
        template: The programme the slots came from.
        slots: Slots carrying an ``exercise_id``.
        catalog: Exercise metadata keyed by id.

    Returns:
        The assembled plan.
    """
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
    """Check an assembled plan against its template and the catalog.

    Strict, and the failure is an exception rather than an issue: sets and reps
    must still equal the template's, and every exercise id must exist in the
    catalog. A mismatch means the assembly corrupted the plan, which is a bug to
    fix rather than a finding to show the user.

    Args:
        plan: The assembled plan.
        template: The template it was built from.
        catalog: The exercise catalog.

    Raises:
        ValueError: On an unknown exercise, or a prescription that no longer
            matches the template slot it came from.
    """
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


# ----------------------------------------------------------------------
# Issues and rendering
# ----------------------------------------------------------------------


def _split_preference_notes(preferences: str, template: dict, match_count: int) -> list[Issue]:
    """Say out loud when a requested split could not be honoured.

    ``preferences`` reaches the model, which uses it to pick between the legal
    options for a slot. It does **not** reach template selection — days, goal and
    level are the only criteria — so "an upper body focused 4 day plan" silently
    produced the balanced Upper/Lower split, delivered as though it were what was
    asked for. Silence there is the fault: the plan is a reasonable one, it is
    simply not the shape requested.

    Args:
        preferences: The user's stated preferences, free text.
        template: The template that was selected.
        match_count: How many templates matched the hard criteria.

    Returns:
        One ``info`` issue when the user asked for a split, otherwise nothing.
    """
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
    """Explain why a slot could not be filled.

    Args:
        slot: The unfillable template slot.
        profile: User profile, for naming the constraint responsible.

    Returns:
        The issue to surface.
    """
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
        # Human-readable, like every other issue location: this string is shown
        # to the user, not matched on.
        location=f"{slot['day_name']} / {slot['pattern'].replace('_', ' ')}",
        message=message,
        suggestion=None,
        rubric_ref=rubric_ref,
    )


def _issue(severity: str, location: str, message: str, rubric_ref: str) -> Issue:
    """Build a planning issue.

    Args:
        severity: ``"info"``, ``"warn"`` or ``"block"``.
        location: Where the problem is.
        message: User-facing explanation.
        rubric_ref: Dotted reference for traceability.

    Returns:
        The issue.
    """
    return Issue(
        source="volume",
        severity=severity,
        location=location,
        message=message,
        suggestion=None,
        rubric_ref=rubric_ref,
    )


def _as_issues(notes: list[dict[str, Any]]) -> list[Issue]:
    """Re-type notes read back out of state.

    State round-trips a ``TypedDict`` as a plain dict; the annotation is for the
    reader, and this is where it is restated.

    Args:
        notes: Setup findings from state.

    Returns:
        The same findings, typed.
    """
    return [Issue(**note) for note in notes]


def _render_slots(slots: list[dict], notes: list[Issue]) -> str:
    """Render the slot list as the tool's result.

    Args:
        slots: Slots with their candidates.
        notes: Setup findings, included so the model can mention them.

    Returns:
        Compact JSON the model can read without ambiguity.
    """
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


def _render_commit_result(draft: drafts.Draft) -> str:
    """Render what committing produced, for the model to act on.

    The plan comes back as text rather than JSON. The model describes it; it
    does not reassemble it, and giving it structure to copy is how a set count
    changes on its way to the answer.

    Args:
        draft: The draft just minted.

    Returns:
        The result as JSON with the plan pre-rendered inside it.
    """
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


def _render_refusal(notes: list[Issue]) -> str:
    """Render why no plan can be produced at all.

    Args:
        notes: The blocking findings.

    Returns:
        Text naming the conflict, so the model reports it rather than retrying.
    """
    if not notes:
        return "No plan can be produced for this profile, and no reason was recorded."
    return "No plan can be produced. " + " ".join(note["message"] for note in notes)


def _tool_error(tool_call_id: str, message: str) -> Command:
    """Return a tool failure the model can recover from.

    Args:
        tool_call_id: The call being answered.
        message: What went wrong and what to do instead.

    Returns:
        A command carrying the error as this call's result.
    """
    return Command(
        update={
            "messages": [ToolMessage(content=message, tool_call_id=tool_call_id, status="error")]
        }
    )


__all__ = ["commit_draft", "get_exercise_candidates", "get_template_slots", "tools"]
