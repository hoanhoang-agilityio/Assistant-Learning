"""Nodes of the ingest agent."""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from app.core.langgraph.agents.ingest.prompts import load_parse_plan_prompt
from app.core.langgraph.agents.ingest.state import IngestState, ParsedPlan
from app.core.langgraph.utils import dump_messages
from app.core.logging import logger
from app.services.exercise_resolver import resolve_exercise
from app.services.llm.service import llm_service

_PARSER_MODEL = "gpt-5-mini"
_CONTEXT_TURNS = 4


async def parse_plan(state: IngestState, config: RunnableConfig) -> Command:
    """Read the pasted plan into days and exercise lines.

    Reads ``messages``. Writes ``submitted_plan``.

    The model transcribes; it does not identify exercises. Names are carried
    through verbatim so ``resolve_names`` can match them against the catalog and
    report its confidence — a model that "helpfully" normalised
    "leg press" to "leg extension" here would destroy the only evidence that the
    match was uncertain.

    Args:
        state: Current ingest state.
        config: Runnable config. Callbacks propagate through contextvars.

    Returns:
        A command going to ``resolve_names``, or to ``END`` when there is no
        plan in the message.
    """
    conversation = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in dump_messages(state["messages"][-_CONTEXT_TURNS:])
    )

    try:
        parsed = await llm_service.call(
            [HumanMessage(content=load_parse_plan_prompt(conversation))],
            model_name=_PARSER_MODEL,
            response_format=ParsedPlan,
        )
    except Exception as e:
        logger.exception("ingest_parse_failed", error=str(e))
        return Command(update={"submitted_plan": None}, goto=END)

    if not parsed.is_a_plan or not parsed.days:
        return Command(update={"submitted_plan": None}, goto=END)

    return Command(
        update={"submitted_plan": parsed.model_dump(exclude={"is_a_plan"})},
        goto="resolve_names",
    )


async def resolve_names(state: IngestState, config: RunnableConfig) -> Command:
    """Match each written exercise name onto a catalog id.

    Reads ``submitted_plan`` and ``catalog``. Writes ``submitted_plan``,
    ``unresolved`` and ``incomplete``.

    A name that cannot be matched confidently is recorded in ``unresolved``
    rather than resolved to the closest option.
    Guessing here is the most damaging failure available to this branch: the
    plan gets reviewed, the review looks authoritative, and it describes
    exercises the user is not doing.

    Args:
        state: Current ingest state.
        config: Runnable config. Unused — matching is deterministic.

    Returns:
        A command going to ``END`` with whatever could be resolved.
    """
    catalog = state["catalog"]
    parsed = state["submitted_plan"] or {}

    days: list[dict] = []
    unresolved: list[dict] = []
    incomplete: list[str] = []

    for index, day in enumerate(parsed.get("days") or []):
        exercises: list[dict] = []
        day_name = day.get("name") or f"Day {index + 1}"

        for entry in day.get("exercises") or []:
            raw_name = entry.get("raw_name", "")
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
                    "slot_id": f"submitted_{len(days)}_{len(exercises)}",
                    "exercise_id": exercise_id,
                    "name": catalog[exercise_id]["name"],
                    "sets": entry["sets"],
                    "reps": entry["reps"],
                    "rir": entry.get("rir") or [2, 3],
                }
            )

        if exercises:
            days.append({"name": day_name, "exercises": exercises})

    logger.info(
        "ingest_names_resolved",
        resolved=sum(len(day["exercises"]) for day in days),
        unresolved=len(unresolved),
        incomplete=len(incomplete),
    )
    return Command(
        update={
            "submitted_plan": {"days": days} if days else None,
            "unresolved": unresolved,
            "incomplete": incomplete,
        },
        goto=END,
    )
