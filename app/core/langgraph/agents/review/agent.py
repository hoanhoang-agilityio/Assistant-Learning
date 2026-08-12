"""The review agent, declared rather than assembled."""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.review.prompts import load_review_agent_prompt
from app.core.langgraph.agents.review.state import ReviewState
from app.core.langgraph.agents.review.tools import tools
from app.core.langgraph.models import default_model, resilience_middleware

AGENT_NAME = "review"

_MAX_LOOKUPS = 6

_MAX_SCORES = 2

_MAX_MODEL_CALLS = _MAX_LOOKUPS + _MAX_SCORES + 2


def review_agent() -> CompiledStateGraph:
    """Build the review agent."""

    middleware: list[AgentMiddleware] = [*resilience_middleware()]
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
        system_prompt=load_review_agent_prompt(),
        tools=tools,
        state_schema=ReviewState,
        middleware=tuple(middleware),
        name=AGENT_NAME,
    )


__all__ = ["AGENT_NAME", "review_agent"]
