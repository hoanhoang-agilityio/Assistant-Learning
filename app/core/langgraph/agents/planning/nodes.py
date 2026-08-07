"""Nodes of the planning agent.

Three deterministic nodes around one LLM node. That ratio is the design
The template fixes the programme, the catalog filter
fixes the legal options, and the model's entire contribution is picking one
option per slot from a list it cannot extend.
"""

import json

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from app.core.langgraph.agents.planning.prompts import load_choose_exercises_prompt
from app.core.langgraph.agents.planning.state import ExerciseChoices, PlanningState
from app.core.langgraph.rubrics import CONTRAINDICATIONS
from app.core.langgraph.templates import iter_slots, query_templates
from app.core.logging import logger
from app.schemas.graph import Issue
from app.services.catalog import (
    candidates_for_slot,
    forbidden_joint_actions,
    forbidden_loaded_positions,
)
from app.services.llm.service import llm_service

_CHOOSER_MODEL = "gpt-5-mini"


async def select_template(state: PlanningState, config: RunnableConfig) -> Command:
    """Pick the programme skeleton matching the user's hard constraints.

    Reads ``profile`` and ``goal``. Writes ``template``, ``slots`` and ``issues``.

    Takes the most popular match rather than asking a model: days per week, goal
    and level are exact criteria, so there is nothing to judge (§6.1).

    No matching template is a *conflicting constraint*, and it is reported here
    rather than later. Discovering at verify time that six sessions a week with
    only resistance bands has no programme wastes the whole pipeline and gives
    the user a worse explanation (§12).

    Args:
        state: Current planning state.
        config: Runnable config. Unused — this node performs no I/O.

    Returns:
        A command going to ``filter_candidates``, or to ``END`` with a blocking
        issue when no template fits.
    """
    profile = state["profile"]
    days = profile.get("days_per_week")
    level = profile.get("level", 1)

    matches = query_templates(days_per_week=days, goal=state["goal"], level=level)
    if not matches:
        return Command(
            update={
                "issues": [
                    Issue(
                        source="volume",
                        severity="block",
                        location="Programme",
                        message=(
                            f"No programme template matches {days} sessions a week for a "
                            f"{state['goal']} goal at your experience level. Try a different "
                            "number of sessions."
                        ),
                        suggestion=None,
                        rubric_ref="templates.no_match",
                    )
                ]
            },
            goto=END,
        )

    template = matches[0]

    return Command(
        update={"template": template, "slots": iter_slots(template)}, goto="filter_candidates"
    )


async def filter_candidates(state: PlanningState, config: RunnableConfig) -> Command:
    """Attach the legal exercise options to every slot.

    Reads ``slots``, ``profile`` and ``catalog``. Writes ``slots`` and ``issues``.

    A slot with no legal candidate is dropped and reported, not failed. That case
    is reachable and correct: shoulder impingement rules out overhead abduction,
    and every vertical press involves it, so the honest outcome is a plan without
    that slot plus a line saying why — not a refusal to produce a plan.

    Every legal candidate is attached, with no exclusion for exercises used by an
    earlier slot. Avoiding repeats across the week is ``choose_exercises``'s job
    (§6.3), and doing it here would be wrong twice over: it reserves an exercise
    the model has not chosen yet, and it shrinks later slots' lists on the
    strength of that guess — which can empty a slot that had legal options.

    Args:
        state: Current planning state.
        config: Runnable config. Unused — the catalog is already in state.

    Returns:
        A command going to ``choose_exercises``, or to ``END`` when nothing at
        all can be filled.
    """
    profile = state["profile"]
    catalog = state["catalog"]
    forbidden_actions = forbidden_joint_actions(profile, CONTRAINDICATIONS)
    forbidden_positions = forbidden_loaded_positions(profile, CONTRAINDICATIONS)

    fillable: list[dict] = []
    issues: list[Issue] = []

    for slot in state["slots"]:
        candidates = candidates_for_slot(
            slot, profile, catalog, forbidden_actions, forbidden_positions
        )
        if not candidates:
            issues.append(_dropped_slot_issue(slot, profile))
            continue
        fillable.append({**slot, "candidates": candidates})

    if not fillable:
        return Command(update={"slots": [], "issues": issues}, goto=END)
    return Command(update={"slots": fillable, "issues": issues}, goto="choose_exercises")


async def choose_exercises(state: PlanningState, config: RunnableConfig) -> Command:
    """Fill each slot with one exercise from its candidate list.

    Reads ``slots`` and ``preferences``. Writes ``slots``.

    The only place a model participates in building a plan. Its output is
    validated against each slot's candidate list, and an id that is not there is
    replaced with the first candidate — so a hallucinated or contraindicated
    exercise cannot enter the plan even if the model returns one. The same
    fallback covers a failed call, which is why this node has no error branch.

    Args:
        state: Current planning state.
        config: Runnable config. Callbacks propagate to the LLM call through
            contextvars.

    Returns:
        A command writing the chosen exercise onto each slot and going to
        ``assemble_plan``.
    """
    slots = state["slots"]

    try:
        decision = await llm_service.call(
            [
                HumanMessage(
                    content=load_choose_exercises_prompt(
                        slots=_render_slots(slots), preferences=state.get("preferences", "")
                    )
                )
            ],
            model_name=_CHOOSER_MODEL,
            response_format=ExerciseChoices,
        )
        chosen = {choice.slot_id: choice.exercise_id for choice in decision.choices}
    except Exception as e:
        # Not an error branch: every slot already has a valid default, so the
        # plan is still correct — only less varied.
        logger.exception("planning_choose_failed_using_defaults", error=str(e))
        chosen = {}

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
            # Fall back to the first candidate not already used this week, so
            # the deterministic path still varies the plan. If every candidate
            # is taken, repeat rather than leave the slot empty.
            exercise_id = next(
                (c["exercise_id"] for c in slot["candidates"] if c["exercise_id"] not in used),
                slot["candidates"][0]["exercise_id"],
            )

        used.add(exercise_id)
        filled.append({**slot, "exercise_id": exercise_id})

    logger.info(
        "planning_exercises_chosen",
        slots=len(filled),
        model_choices=len(chosen),
        rejected=rejected,
    )
    return Command(update={"slots": filled}, goto="assemble_plan")


async def assemble_plan(state: PlanningState, config: RunnableConfig) -> Command:
    """Build the plan JSON and validate it against the template it came from.

    Reads ``template``, ``slots`` and ``catalog``. Writes ``draft_plan``.

    Validation is strict and the failure is an exception, not an issue: sets and
    reps must still equal the template's, and every exercise id must exist in the
    catalog. A mismatch means an earlier node corrupted the plan, which is a bug
    to fix rather than a finding to show the user (§6.4).

    Args:
        state: Current planning state.
        config: Runnable config. Unused — this node performs no I/O.

    Returns:
        A command writing ``draft_plan`` and going to ``END``.

    Raises:
        ValueError: When the assembled plan does not match its template or
            references an exercise outside the catalog.
    """
    template = state["template"]
    catalog = state["catalog"]
    by_day: dict[str, list[dict]] = {}

    for slot in state["slots"]:
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

    plan = {
        "template_id": template["template_id"],
        "days": [
            {"name": day["name"], "exercises": by_day[day["name"]]}
            for day in template["days"]
            if day["name"] in by_day
        ],
    }

    _validate(plan, template, catalog)
    logger.info(
        "planning_plan_assembled",
        template_id=template["template_id"],
        days=len(plan["days"]),
        exercises=sum(len(day["exercises"]) for day in plan["days"]),
    )
    return Command(update={"draft_plan": plan}, goto=END)


def _validate(plan: dict, template: dict, catalog: dict) -> None:
    """Check an assembled plan against its template and the catalog.

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


def _render_slots(slots: list[dict]) -> str:
    """Render slots and their candidates for the prompt.

    Args:
        slots: Slots carrying a ``candidates`` list.

    Returns:
        Compact JSON the model can read without ambiguity.
    """
    return json.dumps(
        [
            {
                "slot_id": slot["slot_id"],
                "day": slot["day_name"],
                "pattern": slot["pattern"],
                "candidates": [
                    {
                        "exercise_id": c["exercise_id"],
                        "name": c["name"],
                        "equipment": c["equipment"],
                    }
                    for c in slot["candidates"]
                ],
            }
            for slot in slots
        ],
        ensure_ascii=False,
        indent=1,
    )
