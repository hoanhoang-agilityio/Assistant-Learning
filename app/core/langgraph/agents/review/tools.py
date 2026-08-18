"""Tools of the review agent."""

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.core.langgraph.plans.rendering import render_plan
from app.core.langgraph.verification.scoring import score, sort_issues
from app.schemas.graph import Issue, PastedDay, ReviewEnvelope
from app.services.catalog import load_catalog
from app.services.exercise_resolver import resolve_exercise

_DEFAULT_RIR = [2, 3]


@tool
def lookup_exercise(raw_text: str, runtime: ToolRuntime) -> str:
    """Look up what a written exercise name refers to in the catalog.

    Use this when ``score_plan`` reported a line it could not identify and you
    want the options to put to the user. You do not need to call it for every
    line — ``score_plan`` resolves names itself.

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
    answer = {
        "raw_name": raw_text,
        "exercise_id": exercise_id,
        "name": catalog[exercise_id]["name"],
        "confidence": resolution["confidence"],
    }
    if resolution["equivalent"]:
        answer["also_matched"] = resolution["equivalent"]
        answer["note"] = (
            "The name fits several catalog entries that every check reads identically, so "
            "the one above was used. Say which one you assessed if you mention this line."
        )
    return json.dumps(answer, ensure_ascii=False)


@tool
async def score_plan(runtime: ToolRuntime) -> Command:
    """Assess the plan the user pasted: resolve its exercises, compute macros, run the rubrics.


    This is read-only. It produces an assessment, not a plan that can be saved.

    """
    catalog = runtime.state.get("catalog") or load_catalog()
    days = runtime.state.get("submitted") or []
    plan, unresolved, incomplete, assumed = _resolve_days(days, catalog)

    if not plan["days"]:
        line_count = sum(len(day.exercises) for day in days)
        return Command(
            update={
                "submitted_plan": None,
                "unresolved": unresolved,
                "incomplete": incomplete,
                "scored": False,
                "messages": [
                    ToolMessage(
                        content=_render_nothing_understood(unresolved, incomplete, line_count),
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ],
            }
        )

    profile = runtime.state.get("profile") or {}
    macros, issues, verdict = await score(plan, profile)
    # Some lines resolved and some did not. The plan is assessed on what was
    # understood, and the rest is reported — an assessment that quietly ignores
    # three exercises is worse than one that names them.
    all_issues = _ingest_notes(unresolved, incomplete, assumed) + issues

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
    days: list[PastedDay], catalog: dict[str, dict]
) -> tuple[dict[str, Any], list[dict], list[str], list[dict]]:
    """Match every written exercise name onto a catalog id.

    A name that cannot be matched confidently is recorded rather than resolved
    to the closest option. Guessing here is the most damaging failure available
    to this agent: the plan gets reviewed, the review looks authoritative, and it
    describes exercises the user is not doing.

    Nothing is dropped without landing in ``unresolved`` or ``incomplete``. The
    shape checks that used to ``continue`` silently are gone — the transcription
    schema performs them now, and a line the schema admits but the catalog does
    not is a finding, not a deletion.

    """
    resolved_days: list[dict] = []
    unresolved: list[dict] = []
    incomplete: list[str] = []
    assumed: list[dict] = []

    for index, day in enumerate(days or []):
        day_name = day.name or f"Day {day.day or index + 1}"
        exercises: list[dict] = []

        for entry in day.exercises:
            raw_name = entry.raw_name.strip()
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

            reps = _range(entry.reps_min, entry.reps_max)
            if not entry.sets or not reps:
                # Volume cannot be counted without both, and assuming a typical
                # value would put invented sets into a real assessment.
                incomplete.append(f"{day_name} / {raw_name}")
                continue

            exercise_id = resolution["exercise_id"]
            if resolution["equivalent"]:
                # Resolved, but the name fitted several rows the checks read
                # identically. Reported rather than assumed silently: the user
                # is the only one who knows which variant they actually do, and
                # the rendering will name the one that was used.
                assumed.append(
                    {
                        "raw_name": raw_name,
                        "day": day_name,
                        "used": catalog[exercise_id]["name"],
                        "equivalent": resolution["equivalent"],
                    }
                )
            exercises.append(
                {
                    "slot_id": f"submitted_{len(resolved_days)}_{len(exercises)}",
                    "exercise_id": exercise_id,
                    "name": catalog[exercise_id]["name"],
                    "sets": entry.sets,
                    "reps": reps,
                    "rir": _range(entry.rir_min, entry.rir_max) or _DEFAULT_RIR,
                }
            )

        if exercises:
            resolved_days.append({"name": day_name, "exercises": exercises})

    return {"days": resolved_days}, unresolved, incomplete, assumed


def _range(low: int | None, high: int | None) -> list[int] | None:
    """Pair a transcribed low and high into the range every consumer indexes.

    One end is enough: "4x8" is a range whose ends are equal, and a user who
    wrote "8-12" but whose transcription lost an end is better served by the end
    that survived than by having the line dropped.

    Args:
        low: Low end, or ``None`` when the user gave none.
        high: High end, or ``None``.

    Returns:
        A two-element range, or ``None`` when neither end was given.
    """
    if low is None and high is None:
        return None
    first = low if low is not None else high
    second = high if high is not None else low
    return [first, second]


def _ingest_notes(
    unresolved: list[dict], incomplete: list[str], assumed: list[dict]
) -> list[Issue]:
    """Report the parts of a pasted plan that could not be read as written.

    Carried as issues so they travel to the answer through the same channel as
    every rubric finding. That is what stops a review quietly omitting three
    exercises it did not understand and still reading as a complete assessment.

    ``assumed`` is the mildest of the three and the only one that is `info`: the
    line *was* assessed, and correctly, because the variants it also matched are
    ones no check can distinguish. It is still said out loud, because the user
    will see a name in the rendering that is not the one they typed.

    """
    notes: list[Issue] = []

    for entry in unresolved:
        options = ", ".join(candidate["name"] for candidate in entry["candidates"])
        suffix = f" Did you mean: {options}?" if options else ""
        # A nameless line is a transcription fault, not an unrecognised exercise.
        # Saying "I couldn't identify ''" would send the user hunting for a
        # problem in their own text that isn't there.
        message = (
            f"An exercise line in {entry['day']} arrived with no name, so it was left out of "
            "the review."
            if not entry["raw_name"]
            else (
                f"I couldn't confidently identify '{entry['raw_name']}', so it was left "
                f"out of the review.{suffix}"
            )
        )
        notes.append(
            Issue(
                source="volume",
                severity="warn",
                location=f"{entry['day']} / {entry['raw_name'] or 'unnamed line'}",
                message=message,
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

    for entry in assumed:
        others = ", ".join(option["name"] for option in entry["equivalent"])
        notes.append(
            Issue(
                source="volume",
                severity="info",
                location=f"{entry['day']} / {entry['raw_name']}",
                message=(
                    f"'{entry['raw_name']}' matches several catalog entries, so it was assessed "
                    f"as {entry['used']}. {others} would have scored identically — same muscles, "
                    "same joint actions — so this changes nothing in the findings above."
                ),
                suggestion={"used": entry["used"], "equivalent": entry["equivalent"]},
                rubric_ref="ingest.variant_assumed",
            )
        )

    return notes


def _render_nothing_understood(
    unresolved: list[dict], incomplete: list[str], line_count: int
) -> str:
    """Say why nothing could be assessed, naming what was unclear.

    Asking the user to paste their plan again is now an honest answer, which it
    was not before. It used to be the response to an empty *transcription* —
    the model's own reading, sent back to the user as though their text were at
    fault, so re-pasting could not change the outcome. Reading the message no
    longer happens here (``transcribe.py``), and the caller refuses before this
    tool is reached when nothing was read at all.

    Args:
        unresolved: Lines whose names no catalog entry matched.
        incomplete: Lines with no sets or reps.
        line_count: How many exercise lines were transcribed at all.

    Returns:
        The tool's error content.
    """
    if line_count == 0 or (not unresolved and not incomplete):
        return (
            "No plan was read from the user's message, so there is nothing to assess. Ask "
            "them to paste it with each day, the exercises under it, and sets and reps for "
            "each."
        )

    problems = [f"'{entry['raw_name'] or 'unnamed line'}' ({entry['day']})" for entry in unresolved]
    problems.extend(f"{location} has no sets or reps" for location in incomplete)
    return (
        "None of the plan could be assessed. Unclear: "
        + "; ".join(problems)
        + ". Ask the user to clarify those rather than assuming."
    )


__all__ = ["lookup_exercise", "score_plan", "tools"]
