"""The middleware that replaces the spine.

Under the old root graph, four nodes ran before anything branched — ``classify``,
``load_context``, ``extract_profile``, ``check_required`` — and the guarantee
that none of them could be skipped came from topology: ``check_required`` was
the only edge into the only branch point. An agent has no edges to express that
with, so each guarantee has to land somewhere else
(``docs/supervisor-architecture.md`` §2).

The ones that must run every turn regardless of what the model does land here.
Middleware hooks compile to real nodes, so they cannot be skipped — a model that
decides the topic gate is unnecessary does not get a say.

Hook order is not cosmetic. ``before_agent`` hooks run before any
``before_model`` hook, and within a phase they run in the order the middleware
list declares. The topic gate must come first: today an off-topic turn writes
nothing to the profile because the extractor returns early on that intent, and
after the conversion that property comes from ordering alone.
"""

import asyncio
from typing import Any

from langchain.agents.middleware import ModelRequest, before_agent, before_model, dynamic_prompt
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.config import get_config
from langgraph.runtime import Runtime

from app.core.langgraph.plans.rendering import render_plan_context
from app.core.langgraph.runtime.context import get_session_id, get_user_id
from app.core.langgraph.runtime.messages import dump_messages
from app.core.langgraph.supervisor.classification import CONTEXT_TURNS, llm_classify
from app.core.langgraph.supervisor.profile_extraction import clean_extraction, goal_conflict
from app.core.langgraph.supervisor.prompt_context import render_semantic_context
from app.core.langgraph.supervisor.prompts import (
    load_extract_profile_prompt,
    load_supervisor_prompt,
)
from app.core.langgraph.supervisor.state import NEW_TURN, SupervisorState
from app.core.logging import logger
from app.schemas.graph import ProfileExtraction
from app.services import profile as profile_service
from app.services.episodes import recent_episodes
from app.services.llm.service import llm_service
from app.services.versions import latest_version

_EXTRACTOR_MODEL = "gpt-5-mini"

# Enough to catch an answer to the previous turn's question without paying for
# the whole history on every extraction.
_EXTRACTION_TURNS = 8

# The whole reply to an off-topic message. Deliberately a constant and not a
# model call: the one thing this branch must never do is engage with the message
# it is declining, and a model handed that message will find a way to help with
# it. It also never enters the agent loop, so there is no tool it could reach.
OFF_TOPIC_ANSWER = (
    "That's outside what I do — I only work on training plans and the nutrition "
    "that goes with them. Ask me about your plan, your training, or anything "
    "about lifting and eating for it."
)


@before_agent(state_schema=SupervisorState, can_jump_to=["end"])
async def topic_gate(state: SupervisorState, runtime: Runtime) -> dict[str, Any] | None:
    """Refuse an out-of-scope message before the supervisor ever sees it.

    Reads ``messages``. Writes the ``NEW_TURN`` reset and ``intent_hint``, or
    ends the turn with the refusal.

    ``classify`` does not die in the conversion — it moves in here, and its
    output is used for two things instead of one: the topic decision, and the
    hint. That is what keeps the gate from costing an extra round-trip, which is
    the standing objection to a separate guardrail node.

    ``before_agent`` rather than ``before_model``: the topic of a turn does not
    change between iterations of the loop, so classifying on every model call
    pays three times for one answer.

    A classification failure does **not** decline. The topic gate is a decision
    the classifier makes, and a classifier that just failed has made no
    decision; turning a bad minute for the model into a refusal aimed at the
    user is the worse of the two errors.

    Args:
        state: Current supervisor state.
        runtime: Agent runtime. Unused — the classifier reads only messages.

    Returns:
        State updates, or the refusal plus a jump to the end of the turn.
    """
    conversation = _conversation(state, CONTEXT_TURNS)

    try:
        decision = await llm_classify(conversation)
    except Exception as e:
        logger.exception("routing_classify_failed_hint_unset", error=str(e))
        return dict(NEW_TURN)

    if decision.intent == "off_topic":
        logger.info("routing_declined_off_topic")
        return {
            **NEW_TURN,
            "messages": [AIMessage(content=OFF_TOPIC_ANSWER)],
            "jump_to": "end",
        }

    logger.info("routing_intent_hint", intent=decision.intent)
    return {**NEW_TURN, "intent_hint": decision.intent}


@before_agent(state_schema=SupervisorState)
async def load_context(state: SupervisorState, runtime: Runtime) -> dict[str, Any]:
    """Load everything this turn knows about the user before it does anything.

    Reads ``plan`` to decide whether to rehydrate it; the owner comes from the
    config. Writes ``profile``, ``episodic_context`` and — only on a session with
    no plan yet — ``plan``, ``macros`` and ``current_version_id``.

    A hook rather than a tool: these are the same queries every turn, keyed on
    ids the hook is handed, so there is nothing for a model to decide and no
    reason to spend a round-trip letting it. Exposing them as tools would only
    create a way to skip them.

    ``plan`` is rehydrated **only when state has none**. Inside a session the
    checkpointer is the source of truth, and the database — which holds only
    approved versions — must not overwrite what this conversation is holding.

    The three reads are independent, so they are gathered rather than awaited in
    sequence.

    Args:
        state: Current supervisor state.
        runtime: Agent runtime. Unused — ids come from the runnable config.

    Returns:
        The loaded context.
    """
    config = get_config()
    user_id = get_user_id(config)
    if user_id is None:
        # Anonymous session: nothing stored, and nothing to store. The profile
        # preconditions still run, so the user is asked for what this turn needs.
        logger.info("context_anonymous_session")
        return {"profile": {}, "episodic_context": ""}

    session_id = get_session_id(config)
    stored, latest, episodes = await asyncio.gather(
        profile_service.get_profile(user_id),
        latest_version(user_id),
        # Excludes the current session — the checkpointer already replays this
        # conversation into the transcript.
        recent_episodes(str(user_id), session_id),
    )

    update: dict[str, Any] = {"profile": stored, "episodic_context": episodes}
    if state.get("plan") is None and latest is not None:
        # Macros travel with the plan they were computed for. Rehydrating one
        # without the other gives the answer a plan whose numbers it cannot name.
        update["plan"] = latest.plan
        update["macros"] = latest.macros
        update["current_version_id"] = latest.id

    logger.info(
        "context_loaded",
        user_id=user_id,
        fields=len(stored),
        plan_rehydrated="plan" in update,
        episodes=bool(episodes),
    )
    return update


@before_model(state_schema=SupervisorState)
async def extract_profile(state: SupervisorState, runtime: Runtime) -> dict[str, Any] | None:
    """Merge facts stated in the conversation over the stored profile.

    Reads ``messages`` and ``profile``. Writes ``profile`` and ``goal_conflict``.

    Runs on every turn, not only when something is missing. A user who says
    "actually I'm 73 kg now" three turns in must move the profile — and with it
    ``profile_hash``, so a stored verify report is no longer reused.

    It is a ``before_model`` hook, so it is positioned to fire on each iteration
    of the supervisor's loop, but it re-extracts only when the user has actually
    said something new. Nothing the model does mid-turn changes what the user
    stated, and paying for an extraction per iteration would triple the cost of
    a three-hop turn for an answer that cannot have changed.

    A failed extraction is not an error: the stored profile is still valid, and
    the tools' profile preconditions will ask for whatever is missing.

    Args:
        state: Current supervisor state.
        runtime: Agent runtime. Unused — the user id comes from the config.

    Returns:
        The merged profile and any goal conflict, or ``None`` when there is
        nothing new to read.
    """
    if not _has_new_user_input(state):
        return None

    conversation = _conversation(state, _EXTRACTION_TURNS)

    try:
        extraction = await llm_service.call(
            [HumanMessage(content=load_extract_profile_prompt(conversation))],
            model_name=_EXTRACTOR_MODEL,
            response_format=ProfileExtraction,
        )
    except Exception as e:
        logger.exception("profile_extraction_failed", error=str(e))
        return None

    updates = clean_extraction(extraction)
    stored = state.get("profile") or {}
    merged = {**stored, **updates}
    if "preferences" in updates:
        # The one field that accumulates rather than replaces. `upsert_profile`
        # merges again, against the row it locks, and that is the authority —
        # this merge exists so the answer *this* turn sees what was just said.
        merged["preferences"] = profile_service.merge_preferences(
            stored.get("preferences"), updates["preferences"]
        )

    # Only whether anything moved, to skip a pointless write. Compared against
    # `merged`, not `updates`, so re-stating a preference the profile already
    # holds is not counted as a change.
    changed = any(stored.get(key) != merged[key] for key in updates)
    user_id = get_user_id(get_config())
    if changed and user_id is not None:
        await profile_service.upsert_profile(user_id, updates)

    conflict = goal_conflict(extraction, merged)
    if conflict:
        logger.info("profile_goal_conflict", stored=conflict["stored"], implied=conflict["implied"])

    logger.info("profile_extracted", extracted=sorted(updates), changed=changed)
    return {"profile": merged, "goal_conflict": conflict}


@dynamic_prompt
def supervisor_prompt(request: ModelRequest) -> SystemMessage:
    """Render the supervisor's system prompt from this turn's state.

    A static string cannot carry the profile as it stands after this turn's
    facts were merged, the plan the user holds, or the two questions the turn may
    have to ask — so the prompt is built per call.

    The plan is rendered as read-only text, and the fields still missing are
    named as a list. Neither is an instruction to the model about what to do
    next; both are facts it would otherwise invent.

    Args:
        request: The pending model call, carrying the agent's state.

    Returns:
        The system message to put in front of the conversation.
    """
    state = request.state
    return SystemMessage(
        content=load_supervisor_prompt(
            semantic_context=render_semantic_context(state.get("profile") or {}),
            plan_context=render_plan_context(state.get("plan"), state.get("macros")),
            episodic_context=state.get("episodic_context") or "",
            missing_fields=state.get("missing_fields") or [],
            goal_conflict=state.get("goal_conflict"),
            intent_hint=state.get("intent_hint"),
        )
    )


def _conversation(state: SupervisorState, turns: int) -> str:
    """Render recent turns as ``role: content`` lines.

    Args:
        state: Current supervisor state.
        turns: How many trailing messages to include.

    Returns:
        The conversation as text.
    """
    return "\n".join(
        f"{message['role']}: {message['content']}"
        for message in dump_messages((state.get("messages") or [])[-turns:])
    )


def _has_new_user_input(state: SupervisorState) -> bool:
    """Decide whether the user has said anything since the last extraction.

    The supervisor's loop appends AI and tool messages, never human ones, so a
    turn's last human message is fixed from the moment it starts. Extraction is
    therefore worth exactly one call per turn — and this is how it knows.

    Args:
        state: Current supervisor state.

    Returns:
        ``True`` when the newest message the model has not answered yet is the
        user's.
    """
    messages = state.get("messages") or []
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return True
        if getattr(message, "type", "") in {"ai", "tool"}:
            return False
    return False


# Order is load-bearing. The topic gate runs first so an off-topic turn never
# reaches the extractor — today that property comes from the extractor returning
# early on the intent, and after the conversion it comes from ordering alone.
middleware = [topic_gate, load_context, extract_profile, supervisor_prompt]


__all__ = [
    "OFF_TOPIC_ANSWER",
    "extract_profile",
    "load_context",
    "middleware",
    "supervisor_prompt",
    "topic_gate",
]
