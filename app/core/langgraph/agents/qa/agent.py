"""The general-QA agent, declared rather than assembled."""

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

from app.core.langgraph.agents.qa.prompts import load_qa_agent_prompt
from app.core.langgraph.agents.qa.state import QAState
from app.core.langgraph.agents.qa.tools import estimate_macros, search_knowledge
from app.core.langgraph.models import default_model, resilience_middleware

AGENT_NAME = "qa"

tools = [search_knowledge, estimate_macros]

_MAX_SEARCHES = 4

FAILURE_ANSWER = "I could not answer that just now. Please try again."

EXHAUSTED_ANSWER = (
    "I looked that up a few times without landing on a clear answer. Try asking "
    "it a different way and I'll have another go."
)


@dynamic_prompt
def _qa_prompt(request: ModelRequest) -> SystemMessage:
    """Render the system prompt from what the parent passed in.

    A static ``system_prompt`` string cannot carry this turn's plan or the
    memory retrieved for this user, so the prompt is built per call from state.

    Args:
        request: The pending model call, carrying the agent's state.

    Returns:
        The system message to put in front of the conversation.
    """
    state = request.state
    return SystemMessage(
        content=load_qa_agent_prompt(
            state["plan_context"],
            state.get("episodic_context", ""),
        )
    )


def qa_agent() -> CompiledStateGraph:
    """Build the general-QA agent."""
    middleware: list[AgentMiddleware] = [_qa_prompt, *resilience_middleware()]

    middleware.append(ToolCallLimitMiddleware(run_limit=_MAX_SEARCHES, exit_behavior="continue"))
    middleware.append(ModelCallLimitMiddleware(run_limit=_MAX_SEARCHES + 1, exit_behavior="end"))

    return create_agent(
        model=default_model(),
        tools=tools,
        state_schema=QAState,
        middleware=tuple(middleware),
        name=AGENT_NAME,
    )
