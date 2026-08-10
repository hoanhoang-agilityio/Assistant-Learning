"""The review agent, declared rather than assembled.

Earns agent status for a reason the old two-node ingest pipeline could not
satisfy (``docs/supervisor-architecture.md`` §6): the input is free text of
unknown quality, and the number of rounds it takes to resolve — transcribe, look
a name up, ask, transcribe again — cannot be predicted from a graph edge.

What stays fixed is everything that matters. Names are matched inside tool
bodies, not by the model; the assessment runs every rubric; and no tool here
mints a ``draft_id``, so nothing this agent produces can be saved as the user's
plan.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    ToolCallLimitMiddleware,
    dynamic_prompt,
)
from langchain_core.messages import SystemMessage
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.review.prompts import load_review_agent_prompt
from app.core.langgraph.agents.review.state import ReviewState
from app.core.langgraph.agents.review.tools import tools
from app.core.langgraph.models import default_model, resilience_middleware
from app.core.langgraph.rendering import render_semantic_context

AGENT_NAME = "review"

# Name lookups one review may cost. A plan with a few ambiguous lines needs a
# handful; a model on its tenth is looking up lines `score_plan` would have
# resolved for it.
_MAX_LOOKUPS = 6

# Scoring passes. More than two means the model is re-transcribing the same plan
# rather than reporting what it found.
_MAX_SCORES = 2

_MAX_MODEL_CALLS = _MAX_LOOKUPS + _MAX_SCORES + 2


@dynamic_prompt
def _review_prompt(request: ModelRequest) -> SystemMessage:
    """Render the system prompt from the state the caller mapped in.

    Args:
        request: The pending model call, carrying the agent's state.

    Returns:
        The system message to put in front of the conversation.
    """
    return SystemMessage(
        content=load_review_agent_prompt(
            profile=render_semantic_context(request.state.get("profile") or {})
        )
    )


def build_review_agent() -> CompiledStateGraph:
    """Build the review agent.

    Compiled without a checkpointer — the root graph's persists the whole tree.

    Returns:
        The compiled agent, named so its spans are identifiable in Langfuse.
    """
    middleware: list[AgentMiddleware] = [_review_prompt, *resilience_middleware()]
    middleware.append(
        ToolCallLimitMiddleware(
            tool_name="lookup_exercise", run_limit=_MAX_LOOKUPS, exit_behavior="continue"
        )
    )
    middleware.append(
        ToolCallLimitMiddleware(
            tool_name="score_plan", run_limit=_MAX_SCORES, exit_behavior="continue"
        )
    )
    middleware.append(ModelCallLimitMiddleware(run_limit=_MAX_MODEL_CALLS, exit_behavior="end"))

    return create_agent(
        model=default_model(),
        tools=tools,
        state_schema=ReviewState,
        middleware=tuple(middleware),
        name=AGENT_NAME,
    )


__all__ = ["AGENT_NAME", "build_review_agent"]
