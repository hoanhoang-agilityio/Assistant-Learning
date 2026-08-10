"""The general-QA agent, declared rather than assembled.

An LLM, a tool and a prompt. There are no nodes to write: the model/tool loop,
its exit condition and its error handling are what ``create_agent`` builds, and
the policies around it — retry, model fallback, how many searches one question
may cost — are middleware rather than hand-rolled control flow.

What that costs, and how it is paid back: the agent holds a model directly, so
``llm_service.call`` and the retry and circular fallback built into it are not
on this path. ``ModelRetryMiddleware`` and ``ModelFallbackMiddleware`` restore
both, reading the same retryable-error set and the same registry order, so the
two paths cannot drift into different failure behaviour.
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

from app.core.langgraph.agents.qa.state import QAState
from app.core.langgraph.agents.qa.tools import estimate_macros
from app.core.langgraph.models import default_model, resilience_middleware
from app.core.langgraph.tools import tools as shared_tools
from app.core.prompts import load_qa_prompt

AGENT_NAME = "qa"

# `estimate_macros` is owned by this agent rather than shared, and that is the
# point of it: QA is read-only and has no path to a save, so a hypothetical
# number computed here cannot reach a stored plan. No other agent gets it.
tools = [*shared_tools, estimate_macros]

# Tool calls one question may cost. A knowledge question needs one lookup,
# occasionally two, and a what-if adds one estimate; a model still calling tools
# on the fifth is looping, not researching. `continue` lets it answer with what
# it already retrieved rather than ending the turn on an error the user did not
# cause.
_MAX_SEARCHES = 4

# What the node says when the agent could not produce anything at all. The turn
# stays alive: an apology is a worse answer than a real one, and a better
# outcome than a stack trace reaching the API.
FAILURE_ANSWER = "I could not answer that just now. Please try again."

# What the node says when the agent stopped on its call limit with nothing
# written. Rare, and worth its own wording: nothing failed, the model simply
# never got to an answer.
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
        content=load_qa_prompt(
            state["plan_context"],
            state.get("semantic_context", ""),
            state.get("episodic_context", ""),
        )
    )


def build_qa_agent() -> CompiledStateGraph:
    """Build the general-QA agent.

    Compiled without a checkpointer on purpose: the root graph's checkpointer
    persists the whole tree, and a second one would write a competing history.

    Returns:
        The compiled agent, named so its spans are identifiable in Langfuse.
    """
    middleware: list[AgentMiddleware] = [_qa_prompt, *resilience_middleware()]

    # Two limits, because they stop different things. The tool limit is the
    # normal one: the model is told it has searched enough and answers with what
    # it has. That only works if the model answers — one that emits nothing but
    # tool calls would loop until `recursion_limit` blew the turn up, so the
    # model limit is the hard floor underneath it. One more model call than
    # searches, so the agent always gets its turn to write the answer.
    middleware.append(ToolCallLimitMiddleware(run_limit=_MAX_SEARCHES, exit_behavior="continue"))
    middleware.append(ModelCallLimitMiddleware(run_limit=_MAX_SEARCHES + 1, exit_behavior="end"))

    return create_agent(
        model=default_model(),
        tools=tools,
        state_schema=QAState,
        middleware=tuple(middleware),
        name=AGENT_NAME,
    )
