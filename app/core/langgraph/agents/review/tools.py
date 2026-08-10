"""Tools of the review agent.

Two tools. The model transcribes what the user pasted and hands the lines over;
it never decides what an exercise *is*. That judgment is a three-tier match
against the catalog inside :func:`lookup_exercise` and inside :func:`score_plan`,
and it is deterministic on purpose — a model that "helpfully" normalised
"leg press" to "leg extension" would destroy the only evidence that the match
was uncertain.

Low confidence is reported, never guessed. A review that silently omits three
exercises is worse than one that names them
(``docs/supervisor-architecture.md`` §6.2).

``score_plan`` returns a report and deliberately mints **no** ``draft_id``. That
absence is what keeps a pasted plan from becoming the user's own: a review
produces nothing ``save_plan`` will accept.
"""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.agents.verification import sort_issues
from app.core.langgraph.rendering import render_plan
from app.core.langgraph.scoring import score
from app.core.logging import logger
from app.schemas.graph import Issue, ReviewEnvelope
from app.services.catalog import load_catalog
from app.services.exercise_resolver import resolve_exercise

# What a line is prescribed when the user gave no RIR. Reps and sets are never
# defaulted — a guessed set count is counted as real volume and changes the
# assessment — but RIR affects no check, so refusing a line for want of one
# would drop an exercise the user really is doing.
_DEFAULT_RIR = [2, 3]


@tool
def lookup_exercise(raw_text: str, runtime: ToolRuntime) -> str:
    """Look up what a written exercise name refers to in the catalog.

    Use this when a line is ambiguous and you want to ask the user about it
    before assessing the plan. You do not need to call it for every line —
    ``score_plan`` resolves names itself.

    Args:
        raw_text: The exercise name exactly as the user wrote it.
        runtime: Tool runtime, read for the catalog in state.

    Returns:
        The matched exercise as JSON, or the closest candidates with a null
        match when nothing clears the confidence threshold.
    """
    catalog = runtime.state.get("catalog") or load_catalog()
    resolution = resolve_exercise(raw_text, catalog)

    if resolution["exercise_id"] is None:
        return json.dumps(
            {
                "raw_name": raw_text,
                "exercise_id": None,
                "candidates": resolution["candidates"],
                "note": "No confident match. Ask the user which one they mean; do not pick one.",
            },
            ensure_ascii=False,
        )

    exercise_id = resolution["exercise_id"]
    return json.dumps(
        {
            "raw_name": raw_text,
            "exercise_id": exercise_id,
            "name": catalog[exercise_id]["name"],
            "confidence": resolution["confidence"],
        },
        ensure_ascii=False,
    )


@tool
async def score_plan(days: list[dict], runtime: ToolRuntime) -> Command:
    """Assess a pasted plan: resolve its exercises, compute macros, run the rubrics.

    Pass the plan exactly as the user wrote it. Keep ``raw_name`` verbatim — do
    not correct spelling, expand abbreviations, or map a name onto one you think
    is more standard. Leave ``sets`` and ``reps`` out when the user did not state
    them; never fill in a typical value.

    This is read-only. It produces an assessment, not a plan that can be saved.

    Args:
        days: ``[{"name": "Push A", "exercises": [{"raw_name": "bench",
            "sets": 4, "reps": [6, 8], "rir": [1, 2]}]}]``. ``rir`` is optional.
        runtime: Tool runtime, read for the catalog, the profile and this call's
            id.

    Returns:
        A command writing what was understood into state and reporting the
        verdict, the targets and the findings back to the model.
    """
    catalog = runtime.state.get("catalog") or load_catalog()
    plan, unresolved, incomplete = _resolve_days(days, catalog)

    if not plan["days"]:
        return Command(
            update={
                "submitted_plan": None,
                "unresolved": unresolved,
                "incomplete": incomplete,
                "scored": False,
                "messages": [
                    ToolMessage(
                        content=_render_nothing_understood(unresolved, incomplete),
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ],
            }
        )

    profile = runtime.state.get("profile") or {}
    macros, issues, verdict = await score(plan, profile, runtime.config)
    # Some lines resolved and some did not. The plan is assessed on what was
    # understood, and the rest is reported — an assessment that quietly ignores
    # three exercises is worse than one that names them.
    all_issues = _ingest_notes(unresolved, incomplete) + issues

    # A `ReviewEnvelope`, and its type is the contract: it has no `draft_id`
    # field, so there is nothing here `save_plan` would accept. That absence is
    # what keeps a plan someone was curious about from becoming the plan they
    # follow.
    envelope = ReviewEnvelope(
        status="review",
        plan_rendered=render_plan(plan, macros.get("goal")),
        macros=macros,
        issues=sort_issues(all_issues),
        verdict=verdict,
    )

    logger.info(
        "review_plan_scored",
        verdict=verdict,
        days=len(plan["days"]),
        unresolved=len(unresolved),
        incomplete=len(incomplete),
    )
    return Command(
        update={
            "submitted_plan": plan,
            "unresolved": unresolved,
            "incomplete": incomplete,
            "scored": True,
            "messages": [
                ToolMessage(
                    content=json.dumps(envelope, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


tools = [lookup_exercise, score_plan]


def _resolve_days(
    days: list[dict], catalog: dict[str, dict]
) -> tuple[dict[str, Any], list[dict], list[str]]:
    """Match every written exercise name onto a catalog id.

    A name that cannot be matched confidently is recorded rather than resolved
    to the closest option. Guessing here is the most damaging failure available
    to this agent: the plan gets reviewed, the review looks authoritative, and it
    describes exercises the user is not doing.

    Args:
        days: The plan as the model transcribed it.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(plan, unresolved, incomplete)``.
    """
    resolved_days: list[dict] = []
    unresolved: list[dict] = []
    incomplete: list[str] = []

    for index, day in enumerate(days or []):
        if not isinstance(day, dict):
            continue

        day_name = day.get("name") or f"Day {index + 1}"
        exercises: list[dict] = []

        for entry in day.get("exercises") or []:
            if not isinstance(entry, dict):
                continue

            raw_name = str(entry.get("raw_name") or "")
            resolution = resolve_exercise(raw_name, catalog)

            if resolution["exercise_id"] is None:
                unresolved.append(
                    {
                        "raw_name": raw_name,
                        "day": day_name,
                        "confidence": resolution["confidence"],
                        "candidates": resolution["candidates"],
                    }
                )
                continue

            if not entry.get("sets") or not entry.get("reps"):
                # Volume cannot be counted without both, and assuming a typical
                # value would put invented sets into a real assessment.
                incomplete.append(f"{day_name} / {raw_name}")
                continue

            exercise_id = resolution["exercise_id"]
            exercises.append(
                {
                    "slot_id": f"submitted_{len(resolved_days)}_{len(exercises)}",
                    "exercise_id": exercise_id,
                    "name": catalog[exercise_id]["name"],
                    "sets": entry["sets"],
                    "reps": entry["reps"],
                    "rir": entry.get("rir") or _DEFAULT_RIR,
                }
            )

        if exercises:
            resolved_days.append({"name": day_name, "exercises": exercises})

    return {"days": resolved_days}, unresolved, incomplete


def _ingest_notes(unresolved: list[dict], incomplete: list[str]) -> list[Issue]:
    """Report the parts of a pasted plan that could not be read.

    Carried as issues so they travel to the answer through the same channel as
    every rubric finding. That is what stops a review quietly omitting three
    exercises it did not understand and still reading as a complete assessment.

    Args:
        unresolved: Exercise lines that no catalog entry matched confidently.
        incomplete: Lines missing the sets or reps the volume check needs.

    Returns:
        One ``warn`` issue per problem.
    """
    notes: list[Issue] = []

    for entry in unresolved:
        options = ", ".join(candidate["name"] for candidate in entry["candidates"])
        suffix = f" Did you mean: {options}?" if options else ""
        notes.append(
            Issue(
                source="volume",
                severity="warn",
                location=f"{entry['day']} / {entry['raw_name']}",
                message=(
                    f"I couldn't confidently identify '{entry['raw_name']}', so it was left "
                    f"out of the review.{suffix}"
                ),
                suggestion={"candidates": entry["candidates"]} if entry["candidates"] else None,
                rubric_ref="ingest.unresolved_exercise",
            )
        )

    for location in incomplete:
        notes.append(
            Issue(
                source="volume",
                severity="warn",
                location=location,
                message=(
                    "No sets or reps were given, so this exercise was left out of the volume "
                    "count rather than assumed."
                ),
                suggestion=None,
                rubric_ref="ingest.missing_prescription",
            )
        )

    return notes


def _render_nothing_understood(unresolved: list[dict], incomplete: list[str]) -> str:
    """Say why nothing could be assessed, naming what was unclear.

    Args:
        unresolved: Lines that matched nothing confidently.
        incomplete: Lines missing sets or reps.

    Returns:
        Text for the model to turn into a question.
    """
    if not unresolved and not incomplete:
        return (
            "Nothing plan-shaped was found in what you passed. Ask the user to paste the "
            "plan — days, exercises, and sets and reps for each."
        )

    problems = [f"'{entry['raw_name']}' ({entry['day']})" for entry in unresolved]
    problems.extend(f"{location} has no sets or reps" for location in incomplete)
    return (
        "None of the plan could be assessed. Unclear: "
        + "; ".join(problems)
        + ". Ask the user to clarify those rather than assuming."
    )


__all__ = ["lookup_exercise", "score_plan", "tools"]
