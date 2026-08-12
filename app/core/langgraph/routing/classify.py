"""The intent classifier.

Once a root node, now the body of the supervisor's topic gate. What survives the
conversion is the call itself, and what changed is what its answer is used for:
one output, two jobs. The topic decision ends the turn before the agent loop
starts; the intent becomes ``intent_hint``, which is advisory.

That reuse is what keeps the topic gate from costing an extra round-trip. A
standalone guardrail in front of every turn pays for a second model call to catch
the rare off-topic message, and the classifier was already reading the
conversation anyway (``docs/supervisor-architecture.md`` §4.3).

The hint must stay advisory. A hint that routed would be the router this
architecture replaced, and the supervisor may legitimately disagree with it after
reading a tool result — recovering from a bad first guess is one of the three
things the router could not do.
"""

from langchain_core.messages import HumanMessage

from app.core.langgraph.prompts import load_classify_prompt
from app.schemas.graph import IntentDecision
from app.services.llm.service import llm_service

# Enough context to disambiguate a follow-up ("make it 5 days") without paying
# for the whole history on a routing decision.
CONTEXT_TURNS = 6

_CLASSIFIER_MODEL = "gpt-5-mini"


async def llm_classify(conversation: str) -> IntentDecision:
    """Call the classifier model and return its validated decision.

    Never parsed out of free text: the call passes
    ``response_format=IntentDecision``, so an unroutable answer fails validation
    instead of silently naming a branch.

    Args:
        conversation: Recent turns as ``role: content`` lines.

    Returns:
        The validated intent decision.

    Raises:
        RuntimeError: When every model in the registry fails. The caller decides
            what that means — for the topic gate it means "no decision", not
            "decline".
    """
    return await llm_service.call(
        [HumanMessage(content=load_classify_prompt(conversation))],
        model_name=_CLASSIFIER_MODEL,
        response_format=IntentDecision,
    )


__all__ = ["CONTEXT_TURNS", "llm_classify"]
