"""The planning agent, declared rather than assembled.

The one agent whose nature actually changes under the supervisor architecture
(``docs/supervisor-architecture.md`` §5): choosing exercises used to be a single
structured call validated against a candidate list, and it becomes the agent's
own loop. What was a repair edge in the root graph — verify, fail, swap, verify
again — is now the model calling ``get_exercise_candidates`` and re-committing.

There are no nodes to write. An agent's internal graph is fixed: a ``model``
node, a ``tools`` node, and one node per middleware hook. Deterministic work
lives in tool bodies as plain Python; work that must run every call lives in
middleware.
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

from app.core.langgraph.agents.planning.prompts import load_planning_agent_prompt
from app.core.langgraph.agents.planning.state import PlanningState
from app.core.langgraph.agents.planning.tools import tools
from app.core.langgraph.models import default_model, resilience_middleware
from app.core.langgraph.rendering import render_semantic_context

AGENT_NAME = "planning"

# Commits one plan may cost. The repair loop is the agent's loop now, so the cap
# that used to be `_MAX_REPAIRS` on the root graph moves here — and it is not
# optional. Two failed repairs usually means genuinely conflicting constraints,
# which is a decision for the user; an uncapped loop turns that into a timeout.
#
# `continue` rather than `end`: the agent is told it has committed enough and
# gets to report what is unresolved, rather than the turn dying on a limit the
# user did not cause.
_MAX_COMMITS = 3

# Candidate lookups one plan may cost. Generous relative to commits, because a
# failed verification can name several slots and each one is a separate lookup.
_MAX_CANDIDATE_LOOKUPS = 12

# A floor under a model that only ever emits tool calls. The tool limits above
# only work if the model eventually writes a message; without this one, a model
# that never does would loop until `recursion_limit` blew the turn up.
_MAX_MODEL_CALLS = _MAX_COMMITS + _MAX_CANDIDATE_LOOKUPS + 2


@dynamic_prompt
def _planning_prompt(request: ModelRequest) -> SystemMessage:
    """Render the system prompt from the state the caller mapped in.

    A static ``system_prompt`` cannot carry this turn's mode, profile or change
    delta, so the prompt is built per call from state.

    Args:
        request: The pending model call, carrying the agent's state.

    Returns:
        The system message to put in front of the conversation.
    """
    state = request.state
    return SystemMessage(
        content=load_planning_agent_prompt(
            mode=state.get("mode") or "build",
            profile=render_semantic_context(state.get("profile") or {}),
            preferences=state.get("preferences") or "",
            changes=state.get("changes") or {},
        )
    )


def build_planning_agent() -> CompiledStateGraph:
    """Build the planning agent.

    Compiled without a checkpointer on purpose: the root graph's checkpointer
    persists the whole tree, and a second one would write a competing history.

    Returns:
        The compiled agent, named so its spans are identifiable in Langfuse.
    """
    middleware: list[AgentMiddleware] = [_planning_prompt, *resilience_middleware()]
    middleware.append(
        ToolCallLimitMiddleware(
            tool_name="commit_draft", run_limit=_MAX_COMMITS, exit_behavior="continue"
        )
    )
    middleware.append(
        ToolCallLimitMiddleware(
            tool_name="get_exercise_candidates",
            run_limit=_MAX_CANDIDATE_LOOKUPS,
            exit_behavior="continue",
        )
    )
    middleware.append(ModelCallLimitMiddleware(run_limit=_MAX_MODEL_CALLS, exit_behavior="end"))

    return create_agent(
        model=default_model(),
        tools=tools,
        state_schema=PlanningState,
        middleware=tuple(middleware),
        name=AGENT_NAME,
    )


__all__ = ["AGENT_NAME", "build_planning_agent"]
