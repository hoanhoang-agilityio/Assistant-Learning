"""Nodes of the profile agent."""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from app.core.langgraph.agents.profile.prompts import load_extract_profile_prompt
from app.core.langgraph.agents.profile.state import (
    ACTIVITY_LEVELS,
    GOALS,
    ProfileExtraction,
    ProfileState,
    Sex,
)
from app.core.langgraph.rubrics import CONTRAINDICATIONS
from app.core.langgraph.utils import dump_messages
from app.core.logging import logger
from app.services import profile as profile_service
from app.services.llm.service import llm_service

_EXTRACTOR_MODEL = "gpt-5-mini"

# Enough to catch an answer to the previous turn's question without paying for
# the whole history on every extraction.
_CONTEXT_TURNS = 8

_EQUIPMENT_TOKENS = frozenset(
    {
        "barbell",
        "dumbbell",
        "cable",
        "machine",
        "smith_machine",
        "kettlebell",
        "resistance_band",
        "bodyweight",
        "pull_up_bar",
        "dip_station",
    }
)

_MIN_LEVEL, _MAX_LEVEL = 1, 5


async def load_profile(state: ProfileState, config: RunnableConfig) -> Command:
    """Load the stored profile for this user.

    Reads ``user_id``. Writes ``profile``.

    Deterministic and mandatory, so it is a node rather than a tool: there is
    nothing here for a model to decide.

    Args:
        state: Current profile state.
        config: Runnable config. Unused — the query is not model-driven.

    Returns:
        A command going to ``extract_profile``.
    """
    user_id = state.get("user_id")
    if user_id is None:
        # Anonymous session: nothing stored, and nothing to store. The gate
        # still runs, so the user is asked for what this turn needs.
        logger.info("profile_anonymous_session")
        return Command(update={"profile": {}}, goto="extract_profile")

    stored = await profile_service.get_profile(user_id)
    logger.info("profile_loaded", user_id=user_id, fields=len(stored))
    return Command(update={"profile": stored}, goto="extract_profile")


async def extract_profile(state: ProfileState, config: RunnableConfig) -> Command:
    """Merge facts stated in the conversation over the stored profile.

    Reads ``messages`` and ``profile``. Writes ``profile`` and ``changed``.

    Runs on **every** turn, not only when something is missing. A user who says
    "actually I'm 73kg now" three turns in must move the profile — and with it
    ``profile_hash``, so a stored verify report is no longer reused (§12).

    A failed extraction is not an error: the stored profile is still valid, and
    ``check_required`` will ask for whatever is missing.

    Args:
        state: Current profile state.
        config: Runnable config. Callbacks propagate through contextvars.

    Returns:
        A command going to ``check_required``.
    """
    conversation = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in dump_messages(state["messages"][-_CONTEXT_TURNS:])
    )

    try:
        extraction = await llm_service.call(
            [HumanMessage(content=load_extract_profile_prompt(conversation))],
            model_name=_EXTRACTOR_MODEL,
            response_format=ProfileExtraction,
        )
    except Exception as e:
        logger.exception("profile_extraction_failed", error=str(e))
        return Command(update={"changed": False}, goto="check_required")

    updates = _clean(extraction)
    merged = {**state["profile"], **updates}

    changed = any(state["profile"].get(key) != value for key, value in updates.items())
    if changed and state.get("user_id") is not None:
        await profile_service.upsert_profile(state["user_id"], updates)

    logger.info("profile_extracted", extracted=sorted(updates), changed=changed)
    return Command(update={"profile": merged, "changed": changed}, goto="check_required")


async def check_required(state: ProfileState, config: RunnableConfig) -> Command:
    """Decide whether this intent has everything it needs.

    Reads ``profile`` and ``intent``. Writes ``missing_fields``.

    Deterministic against ``REQUIRED_FIELDS`` (§9.1). Leaving this to a model
    guarantees an eventual turn where it decides the profile looks complete and
    the pipeline proceeds with a missing activity level.

    Args:
        state: Current profile state.
        config: Runnable config. Unused.

    Returns:
        A command going to ``END`` with the missing field list.
    """
    missing = profile_service.missing_fields(state["profile"], state["intent"])
    logger.info(
        "profile_required_checked",
        intent=state["intent"],
        missing_count=len(missing),
        missing=missing,
    )
    return Command(update={"missing_fields": missing}, goto=END)


def _clean(extraction: ProfileExtraction) -> dict:
    """Drop nulls and values outside the controlled vocabularies.

    A token the rest of the system does not recognise is worse than a missing
    one: an unknown ``activity_level`` makes ``calc_macros`` raise, and an
    unknown equipment string silently matches no exercise. Discarding it means
    ``check_required`` asks again, which is the correct recovery.

    Args:
        extraction: The model's structured output.

    Returns:
        Only the fields that are present and valid.
    """
    raw = extraction.model_dump(exclude_none=True)
    clean: dict = {}

    for key, value in raw.items():
        if key == "sex" and value not in Sex:
            _drop(key, value)
        elif key == "activity_level" and value not in ACTIVITY_LEVELS:
            _drop(key, value)
        elif key == "goal" and value not in GOALS:
            _drop(key, value)
        elif key == "level" and not _MIN_LEVEL <= value <= _MAX_LEVEL:
            _drop(key, value)
        elif key == "equipment":
            kept = [item for item in value if item in _EQUIPMENT_TOKENS]
            if kept:
                clean[key] = sorted(set(kept))
        elif key == "unmapped_injury":
            clean[key] = str(value)[:200]
        elif key == "injuries":
            # An empty list is a real answer ("no injuries") and must survive.
            clean[key] = [item for item in value if item in CONTRAINDICATIONS["injuries"]]
        else:
            clean[key] = value

    return clean


def _drop(key: str, value: object) -> None:
    """Log a discarded extraction so a bad prompt is visible in the trace."""
    logger.warning("profile_value_outside_vocabulary", field=key, value=str(value))
