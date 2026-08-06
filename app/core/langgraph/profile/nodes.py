"""Root-graph nodes that load, extract and gate the user's training profile.

Three nodes on the root graph rather than a packaged agent. ``agents/`` holds
independent workflows with their own state and contract — something worth
developing and versioning on its own. This is a straight line that exists purely
to orchestrate the root graph: load what is stored, merge what the user just
said, decide whether the turn may proceed. It has no branching of its own, no
state a caller has to map in and out, and nothing another graph would reuse.
Compare ``routing/``, which is here for the same reason.

The chain is mandatory for every write intent. ``dispatch`` sends all four write
intents to ``load_profile`` and only ``check_required`` has an edge to
``intent_branch``, so there is no path to ``calc_macro`` that skips the gate
(``docs/workflow.md`` §1.2, §9.1).
"""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.core.langgraph.rubrics import CONTRAINDICATIONS
from app.core.langgraph.utils import dump_messages
from app.core.logging import logger
from app.core.prompts import load_extract_profile_prompt
from app.schemas.graph import Issue, ProfileExtraction, RootState
from app.services import profile as profile_service
from app.services.llm.service import llm_service

_EXTRACTOR_MODEL = "gpt-5-mini"

# Enough to catch an answer to the previous turn's question without paying for
# the whole history on every extraction.
_CONTEXT_TURNS = 8

# The vocabularies downstream code matches on. An extraction outside these sets
# is silently dropped rather than stored, because `calc_macros` raises on an
# unknown activity level and `filter_candidates` would silently match nothing
# for an unknown equipment token.
SEXES = ("male", "female")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
GOALS = ("fat_loss", "muscle_gain", "recomp", "general_health")

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


async def load_profile(state: RootState, config: RunnableConfig) -> Command:
    """Load the stored profile for this user.

    Reads nothing from state; the owner comes from ``config``. Writes
    ``profile``.

    Deterministic and mandatory, so it is a node rather than a tool: there is
    nothing here for a model to decide.

    Args:
        state: Current root state. Unused — the query is keyed on the config.
        config: Runnable config, read for ``user_id``.

    Returns:
        A command going to ``extract_profile``.
    """
    user_id = _user_id(config)
    if user_id is None:
        # Anonymous session: nothing stored, and nothing to store. The gate
        # still runs, so the user is asked for what this turn needs.
        logger.info("profile_anonymous_session")
        return Command(update={"profile": {}}, goto="extract_profile")

    stored = await profile_service.get_profile(user_id)
    logger.info("profile_loaded", user_id=user_id, fields=len(stored))
    return Command(update={"profile": stored}, goto="extract_profile")


async def extract_profile(state: RootState, config: RunnableConfig) -> Command:
    """Merge facts stated in the conversation over the stored profile.

    Reads ``messages`` and ``profile``. Writes ``profile``.

    Runs on **every** turn, not only when something is missing. A user who says
    "actually I'm 73kg now" three turns in must move the profile — and with it
    ``profile_hash``, so a stored verify report is no longer reused (§12).

    A failed extraction is not an error: the stored profile is still valid, and
    ``check_required`` will ask for whatever is missing.

    Args:
        state: Current root state.
        config: Runnable config, read for ``user_id``. Callbacks propagate to
            the nested LLM call through contextvars.

    Returns:
        A command going to ``check_required``.
    """
    conversation = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in dump_messages(state.messages[-_CONTEXT_TURNS:])
    )

    try:
        extraction = await llm_service.call(
            [HumanMessage(content=load_extract_profile_prompt(conversation))],
            model_name=_EXTRACTOR_MODEL,
            response_format=ProfileExtraction,
        )
    except Exception as e:
        logger.exception("profile_extraction_failed", error=str(e))
        return Command(goto="check_required")

    updates = _clean(extraction)
    merged = {**state.profile, **updates}

    # Only whether anything moved, for the log and to skip a pointless write.
    # It is not carried in state: no node downstream reads it, and a field
    # nobody reads is one more thing the checkpointer serialises every turn.
    changed = any(state.profile.get(key) != value for key, value in updates.items())
    user_id = _user_id(config)
    if changed and user_id is not None:
        await profile_service.upsert_profile(user_id, updates)

    logger.info("profile_extracted", extracted=sorted(updates), changed=changed)
    return Command(update={"profile": merged}, goto="check_required")


async def check_required(state: RootState, config: RunnableConfig) -> Command:
    """Decide whether this intent has everything it needs.

    Reads ``profile`` and ``intent``. Writes ``missing_fields`` and ``issues``.

    Deterministic against ``REQUIRED_FIELDS`` (§9.1). Leaving this to a model
    guarantees an eventual turn where it decides the profile looks complete and
    the pipeline proceeds with a missing activity level.

    The only node with an edge to ``intent_branch``. That is what makes the
    profile gate unskippable now that the chain is three root nodes rather than
    one — see the module docstring.

    Args:
        state: Current root state.
        config: Runnable config. Unused — no I/O.

    Returns:
        A command going to ``ask_missing`` when anything is outstanding, and to
        ``intent_branch`` otherwise.
    """
    missing = profile_service.missing_fields(state.profile, state.intent or "general_qa")
    logger.info(
        "profile_required_checked",
        intent=state.intent,
        missing_count=len(missing),
        missing=missing,
    )

    return Command(
        update={
            "missing_fields": missing,
            "issues": _unmapped_injury_notes(state.profile, missing),
        },
        goto="ask_missing" if missing else "intent_branch",
    )


def _unmapped_injury_notes(profile: dict, missing: list[str]) -> list[Issue]:
    """Say out loud that a declared injury has no screening rule.

    Silence here reads as "checked and fine", which is the opposite of the
    truth — nothing in the pipeline accounts for it. Carried as an issue so it
    reaches the answer through the same channel as every rubric finding.

    Args:
        profile: The merged profile.
        missing: Fields still outstanding. A turn that is about to ask for more
            information is not the turn to raise this.

    Returns:
        One ``warn`` issue, or an empty list.
    """
    injury = profile.get("unmapped_injury")
    if not injury or missing:
        return []

    return [
        Issue(
            source="injury",
            severity="warn",
            location="Declared injury",
            message=(
                f'You mentioned: "{injury}". I have no '
                "screening rule for that, so nothing in this plan accounts for it. "
                "Treat the exercise selection as unreviewed for that problem, and "
                "see a professional if it is sharp, new or getting worse."
            ),
            suggestion=None,
            rubric_ref="contraindications.unmapped",
        )
    ]


def _user_id(config: RunnableConfig) -> int | None:
    """Read the session owner from the runnable config.

    Args:
        config: The config the root facade built for this turn.

    Returns:
        The user id, or ``None`` for an anonymous session.
    """
    user_id = (config.get("metadata") or {}).get("user_id")
    return int(user_id) if user_id else None


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
        if key == "sex" and value not in SEXES:
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
    """Log a discarded extraction so a bad prompt is visible in the trace.

    Args:
        key: The profile field being discarded.
        value: The value that failed its vocabulary check.
    """
    logger.warning("profile_value_outside_vocabulary", field=key, value=str(value))
