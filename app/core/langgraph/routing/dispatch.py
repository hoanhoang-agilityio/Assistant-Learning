"""Deterministic intent dispatcher.

No LLM call. The classifier already made the judgment; turning that judgment
into a destination is a lookup, and keeping it a lookup is what makes the
mandatory steps downstream unskippable.
"""

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.core.logging import logger
from app.schemas.graph import Intent, RootState

# Every intent maps to exactly one node. A missing key is a bug, not a runtime
# branch — adding an Intent literal without a target here fails the mapping test.
DISPATCH_TARGETS: dict[Intent, str] = {
    "general_qa": "qa",
    # Every write intent enters the profile gate at `load_profile`. There is no
    # edge around it, which is what stops a turn reaching calc_macro without an
    # activity level: the gate runs to `check_required`, and only
    # `check_required` reaches `intent_branch`. Which branch runs afterwards is
    # `intent_branch`'s decision, not this one's.
    "build_plan": "load_profile",
    "change_plan": "load_profile",
    "check": "load_profile",
    "revert": "load_profile",
}

_FALLBACK_TARGET = "qa"


async def dispatch(state: RootState, config: RunnableConfig) -> Command:
    """Route to the agent that handles the classified intent.

    Reads ``intent``. Writes nothing.

    Args:
        state: Current root state, with ``intent`` set by ``classify``.
        config: Runnable config. Unused — this node performs no I/O.

    Returns:
        A command going to the node registered for the intent.
    """
    if state.intent is None:
        logger.warning("routing_dispatch_without_intent")
        return Command(goto=_FALLBACK_TARGET)

    target = DISPATCH_TARGETS.get(state.intent, _FALLBACK_TARGET)
    logger.info("routing_dispatched", intent=state.intent, target=target)
    return Command(goto=target)
