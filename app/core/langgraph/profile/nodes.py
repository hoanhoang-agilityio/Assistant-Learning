"""Root-graph nodes that load context, extract profile facts and gate the turn.

Three nodes on the root graph rather than a packaged agent. ``agents/`` holds
independent workflows with their own state and contract — something worth
developing and versioning on its own. This is a straight line that exists purely
to orchestrate the root graph: load what is stored, merge what the user just
said, decide whether the turn may proceed. It has no branching of its own, no
state a caller has to map in and out, and nothing another graph would reuse.
Compare ``routing/``, which is here for the same reason.

The chain is mandatory for **every** turn, not only the ones that write. The
graph is a single spine — ``classify → load_context → extract_profile →
check_required`` — and ``check_required`` is the only node with an edge to
``intent_branch``, which is the only node with an edge to any branch at all. So
there is no path to ``calc_macro``, or to ``qa``, that skips the gate.

Putting QA inside the chain is what lets a fact stated this turn reach the answer
given this turn: *"I'm 73 kg now, how much protein?"* answered from the stored
row is answered with the old weight. The gate does not block QA —
``REQUIRED_FIELDS["general_qa"]`` is empty, deliberately and load-bearingly so.
"""

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.core.langgraph.utils import dump_messages
from app.core.logging import logger
from app.core.prompts import load_extract_profile_prompt
from app.schemas.graph import GoalConflict, Intent, Issue, ProfileExtraction, RootState
from app.services import profile as profile_service
from app.services.episodes import recent_episodes
from app.services.llm.service import llm_service
from app.services.rubrics import contraindications
from app.services.versions import latest_version

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

# The intents whose turn spends the goal — both run `calc_macro`, where the goal
# picks a deficit or a surplus. `check` scores a plan the user pasted and
# `general_qa` answers a question; interrupting either to confirm a goal would
# be a form in place of an answer, which is what `REQUIRED_FIELDS` keeps empty
# for `general_qa` to prevent.
_GOAL_SENSITIVE_INTENTS: frozenset[Intent] = frozenset({"build_plan", "change_plan"})

# Intents whose turn ends without a plan, and therefore without a rendered issue
# list. `check` is absent: it produces no *new* plan but it does run the
# verifiers and compose a report, so a finding raised on that turn is seen.
_NO_PLAN_INTENTS = frozenset({"general_qa", "off_topic"})


async def load_context(state: RootState, config: RunnableConfig) -> Command:
    """Load everything this turn knows about the user before it does anything.

    Reads ``plan`` from state to decide whether to rehydrate it; the owner comes
    from ``config``. Writes ``profile``, ``episodic_context`` and — only on a
    session that has no plan yet — ``plan`` and ``macros``.

    A node rather than a tool: these are the same queries every turn, keyed on
    ids the node is handed, so there is nothing for a model to decide and no
    reason to spend a round-trip letting it. A node rather than a facade read
    because the graph should not depend on its caller having assembled context
    for it — a direct ``ainvoke`` from a test or from Studio gets a real profile
    here, and each load shows up as a span in the trace.

    The three reads are independent, so they are gathered rather than awaited in
    sequence.

    ``plan`` is rehydrated **only when state has none**. Inside a session the
    checkpointer is the source of truth: it may be holding a patch that has been
    built but not yet approved, and the database — which only has approved
    versions — must not overwrite that. A thread parked at an ``interrupt()``
    resumes from the interrupted node rather than from the entry point, so this
    node does not run again on the turn that approves a staged change.

    Args:
        state: Current root state, read for ``plan``.
        config: Runnable config, read for ``user_id`` and the session id.

    Returns:
        A command going to ``extract_profile``.
    """
    user_id = _user_id(config)
    if user_id is None:
        # Anonymous session: nothing stored, and nothing to store. The gate
        # still runs, so the user is asked for what this turn needs.
        logger.info("context_anonymous_session")
        return Command(update={"profile": {}, "episodic_context": ""}, goto="extract_profile")

    session_id = (config.get("configurable") or {}).get("thread_id", "")
    stored, latest, episodes = await asyncio.gather(
        profile_service.get_profile(user_id),
        latest_version(user_id),
        # Takes the id as text, and excludes the current session — the
        # checkpointer already replays this conversation into the transcript.
        recent_episodes(str(user_id), session_id),
    )

    update: dict[str, Any] = {"profile": stored, "episodic_context": episodes}
    if state.plan is None and latest is not None:
        # Macros travel with the plan they were computed for. Rehydrating one
        # without the other gives the answer a plan whose numbers it cannot name.
        update["plan"] = latest.plan
        update["macros"] = latest.macros

    logger.info(
        "context_loaded",
        user_id=user_id,
        fields=len(stored),
        plan_rehydrated="plan" in update,
        episodes=bool(episodes),
    )
    return Command(update=update, goto="extract_profile")


async def extract_profile(state: RootState, config: RunnableConfig) -> Command:
    """Merge facts stated in the conversation over the stored profile.

    Reads ``messages`` and ``profile``. Writes ``profile``.

    Runs on **every** turn, not only when something is missing. A user who says
    "actually I'm 73kg now" three turns in must move the profile — and with it
    ``profile_hash``, so a stored verify report is no longer reused.

    A failed extraction is not an error: the stored profile is still valid, and
    ``check_required`` will ask for whatever is missing.

    Skipped for ``off_topic``. Now that every turn passes through here, an
    off-topic message would otherwise cost a model call and could write whatever
    the extractor imagined it found in it. The intent is already decided by the
    time this runs, so the skip is deterministic.

    Args:
        state: Current root state.
        config: Runnable config, read for ``user_id``. Callbacks propagate to
            the nested LLM call through contextvars.

    Returns:
        A command going to ``check_required``.
    """
    if state.intent == "off_topic":
        return Command(goto="check_required")

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
    if "preferences" in updates:
        # The one field that accumulates rather than replaces. `upsert_profile`
        # merges again, against the row it locks, and that is the authority —
        # this merge exists so the answer *this* turn sees what was just said.
        merged["preferences"] = profile_service.merge_preferences(
            state.profile.get("preferences"), updates["preferences"]
        )

    # Only whether anything moved, for the log and to skip a pointless write.
    # It is not carried in state: no node downstream reads it, and a field
    # nobody reads is one more thing the checkpointer serialises every turn.
    # Compared against `merged`, not `updates`, so re-stating a preference the
    # profile already holds is not counted as a change.
    changed = any(state.profile.get(key) != merged[key] for key in updates)
    user_id = _user_id(config)
    if changed and user_id is not None:
        await profile_service.upsert_profile(user_id, updates)

    conflict = _goal_conflict(extraction, merged)
    if conflict:
        logger.info(
            "profile_goal_conflict",
            stored=conflict["stored"],
            implied=conflict["implied"],
        )

    logger.info("profile_extracted", extracted=sorted(updates), changed=changed)
    return Command(update={"profile": merged, "goal_conflict": conflict}, goto="check_required")


async def check_required(state: RootState, config: RunnableConfig) -> Command:
    """Decide whether this intent has everything it needs.

    Reads ``profile`` and ``intent``. Writes ``missing_fields`` and ``issues``.

    Deterministic against ``REQUIRED_FIELDS``. Leaving this to a model
    guarantees an eventual turn where it decides the profile looks complete and
    the pipeline proceeds with a missing activity level.

    The only node with an edge to ``intent_branch``, which is what makes the
    profile gate unskippable — see the module docstring.

    Every turn reaches this, including ``general_qa`` and ``off_topic``. Neither
    has an entry in ``REQUIRED_FIELDS``, so neither is ever blocked here, and
    that emptiness is the whole safety property: a question about pain must get
    an answer, not a form. A QA question that needs a number the profile lacks
    is handled in ``qa.md`` by answering in per-kg terms and asking for the
    weight in the same breath.

    Args:
        state: Current root state.
        config: Runnable config. Unused — no I/O.

    Returns:
        A command going to ``ask_missing`` when anything is outstanding, to
        ``ask_goal`` when the turn contradicts the stored goal, and to
        ``intent_branch`` otherwise.
    """
    intent = state.intent or "general_qa"
    missing = profile_service.missing_fields(state.profile, intent)
    logger.info(
        "profile_required_checked",
        intent=state.intent,
        missing_count=len(missing),
        missing=missing,
    )

    # Missing beats conflicting. A profile with nothing in it has no stored goal
    # to contradict, and asking both questions in one turn buries the one the
    # user has to think about under a form.
    if missing:
        goto = "ask_missing"
    elif state.goal_conflict and intent in _GOAL_SENSITIVE_INTENTS:
        goto = "ask_goal"
    else:
        goto = "intent_branch"

    return Command(
        update={
            "missing_fields": missing,
            "issues": _unmapped_injury_notes(state.profile, missing, intent),
        },
        goto=goto,
    )


def _unmapped_injury_notes(profile: dict, missing: list[str], intent: Intent) -> list[Issue]:
    """Say out loud that a declared injury has no screening rule.

    Silence here reads as "checked and fine", which is the opposite of the
    truth — nothing in the pipeline accounts for it. Carried as an issue so it
    reaches the answer through the same channel as every rubric finding.

    Not raised for a turn that produces no plan. The wording is about a plan
    ("nothing in this plan accounts for it"), and ``qa`` and ``decline`` reach
    ``finalize`` without passing ``compose_answer``, the only node that renders
    ``issues`` — so on those turns it would be computed and thrown away. A
    knowledge question is told about the unscreened injury a different way:
    ``unmapped_injury`` is part of ``semantic_context``, and ``qa.md`` says what
    to do with it.

    Args:
        profile: The merged profile.
        missing: Fields still outstanding. A turn that is about to ask for more
            information is not the turn to raise this.
        intent: What this turn is doing. Read-only intents produce no plan.

    Returns:
        One ``warn`` issue, or an empty list.
    """
    injury = profile.get("unmapped_injury")
    if not injury or missing or intent in _NO_PLAN_INTENTS:
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

    ``implied_goal`` is removed here rather than filtered downstream. What this
    returns is merged straight into ``profile``, so leaving it in would store the
    very guess the field exists to avoid storing.

    Args:
        extraction: The model's structured output.

    Returns:
        Only the profile fields that are present and valid.
    """
    raw = extraction.model_dump(exclude_none=True)
    raw.pop("implied_goal", None)
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
            clean[key] = [item for item in value if item in contraindications()["injuries"]]
        else:
            clean[key] = value

    return clean


def _goal_conflict(extraction: ProfileExtraction, merged: dict) -> GoalConflict | None:
    """Decide whether this turn's implied goal contradicts the stored one.

    Deliberately narrow. A conflict needs an implied goal in the vocabulary, a
    stored goal to contradict, and the two to actually differ — anything less is
    not a question worth interrupting the user with.

    Nothing is raised when the user *stated* a goal this turn: ``goal`` has
    already overwritten the stored one by the time this runs, so ``merged``
    holds what they just said and there is nothing to ask about.

    Args:
        extraction: The model's structured output, before cleaning.
        merged: The profile after this turn's stated facts were applied.

    Returns:
        The conflict, or ``None`` when there is nothing to ask.
    """
    implied = extraction.implied_goal
    if implied not in GOALS:
        if implied is not None:
            _drop("implied_goal", implied)
        return None

    stored = merged.get("goal")
    if not stored or stored == implied:
        return None

    return GoalConflict(stored=stored, implied=implied)


def _drop(key: str, value: object) -> None:
    """Log a discarded extraction so a bad prompt is visible in the trace.

    Args:
        key: The profile field being discarded.
        value: The value that failed its vocabulary check.
    """
    logger.warning("profile_value_outside_vocabulary", field=key, value=str(value))
