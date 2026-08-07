"""LLM intent classifier."""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.core.langgraph.utils import dump_messages
from app.core.logging import logger
from app.core.prompts import load_classify_prompt
from app.schemas.graph import NEW_TURN, IntentDecision, RootState
from app.services.llm.service import llm_service

# Enough context to disambiguate a follow-up ("make it 5 days") without paying
# for the whole history on a routing decision.
_CONTEXT_TURNS = 6

# Intents whose verifier selection comes from the pipeline, not the classifier.
# Only `check` lets the user's wording decide which rubrics run.
_NO_SCOPE_INTENTS = frozenset({"build_plan", "change_plan", "revert", "general_qa"})

_CLASSIFIER_MODEL = "gpt-5-mini"


async def classify(state: RootState, config: RunnableConfig) -> Command:
    """Decide which branch handles this turn.

    Reads ``messages``. Writes ``intent``, ``scope``, ``changes`` and the
    ``NEW_TURN`` reset.

    Being the entry node of every run makes this the one place that can clear
    the previous turn's working state, and clearing it is not housekeeping: the
    checkpointer keeps ``issues``, ``draft_plan`` and the rest, so a change turn
    that does not reset composes its answer from the *build's* findings — which
    name the days of a split the user has just replaced. The reset happens
    before the classification, so it applies to the failure path too.

    A classification failure routes to ``general_qa`` rather than raising: the
    worst outcome of that fallback is a plain answer, whereas guessing
    ``change_plan`` would put the user's approved plan on the path to being
    overwritten.

    Args:
        state: Current root state.
        config: Runnable config. Not read directly — LangChain propagates it to
            the nested LLM call through contextvars, so the call still lands in
            the same trace.

    Returns:
        A command writing the routing decision and going to ``dispatch``.
    """
    conversation = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in dump_messages(state.messages[-_CONTEXT_TURNS:])
    )

    try:
        decision = await llm_classify(conversation)
    except Exception as e:
        logger.exception("routing_classify_failed_defaulting_to_qa", error=str(e))
        return Command(
            update={**NEW_TURN, "intent": "general_qa", "scope": [], "changes": {}},
            goto="dispatch",
        )

    scope = decision.scope if decision.intent not in _NO_SCOPE_INTENTS else []
    # Flattened to a plain dict for state: `changes` is consumed by `patch_plan`
    # as a delta, and `exclude_none` means an unmentioned field is absent rather
    # than an explicit null the patcher would have to special-case.
    changes = (
        decision.changes.model_dump(exclude_none=True) if decision.intent == "change_plan" else {}
    )

    logger.info(
        "routing_intent_classified",
        intent=decision.intent,
        scope=scope,
        change_keys=sorted(changes),
    )
    return Command(
        update={**NEW_TURN, "intent": decision.intent, "scope": scope, "changes": changes},
        goto="dispatch",
    )


async def llm_classify(conversation: str) -> IntentDecision:
    """Call the classifier model and return its validated decision.

    Separate from the node so it can be exercised without building a graph.

    Args:
        conversation: Recent turns as ``role: content`` lines.

    Returns:
        The validated intent decision.

    Raises:
        RuntimeError: When every model in the registry fails.
    """
    return await llm_service.call(
        [HumanMessage(content=load_classify_prompt(conversation))],
        model_name=_CLASSIFIER_MODEL,
        response_format=IntentDecision,
    )
