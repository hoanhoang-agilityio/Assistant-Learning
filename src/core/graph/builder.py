from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.graph.routing import route_from_supervisor
from core.hitl.node import invoke_hitl_node
from core.observability.langfuse import supervisor_span_context
from core.observability.tracing import wrap_traced_subgraph_node
from core.persist.node import invoke_persist_node
from core.subgraphs.fitness.graph import invoke_fitness_subgraph
from core.subgraphs.planning.graph import invoke_planning_subgraph
from core.subgraphs.research.graph import invoke_research_subgraph
from core.subgraphs.user.graph import invoke_user_subgraph
from core.subgraphs.verification.graph import invoke_verification_subgraph
from core.subgraphs.wrapper import append_pipeline_steps


def traced_supervisor_node(state: OrchestrationState) -> dict:
    with supervisor_span_context(state) as span:
        result = supervisor_node(state)
        merged = {
            **result,
            "steps": append_pipeline_steps(state, "supervisor", ["route"]),
        }
        if span is not None:
            span.update(output=merged)
        return merged


planning_node = wrap_traced_subgraph_node("planning", invoke_planning_subgraph)
research_node = wrap_traced_subgraph_node("research", invoke_research_subgraph)
fitness_node = wrap_traced_subgraph_node("fitness", invoke_fitness_subgraph)
verification_node = wrap_traced_subgraph_node("verification", invoke_verification_subgraph)
hitl_node = wrap_traced_subgraph_node("hitl", invoke_hitl_node)
persist_node = wrap_traced_subgraph_node("persist", invoke_persist_node)
# The User subgraph pauses via interrupt() (see core.subgraphs.user.graph) and needs the
# parent's checkpointer/config forwarded through to support that -- see wrap_traced_subgraph_node's
# `needs_config` parameter and invoke_user_subgraph's docstring.
user_node = wrap_traced_subgraph_node("user", invoke_user_subgraph, needs_config=True)


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the supervisor-orchestrated LangGraph."""
    graph = StateGraph(OrchestrationState)

    graph.add_node("supervisor", traced_supervisor_node)
    graph.add_node("user", user_node)
    graph.add_node("planning", planning_node)
    graph.add_node("research", research_node)
    graph.add_node("fitness", fitness_node)
    graph.add_node("verification", verification_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("persist", persist_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "user": "user",
            "planning": "planning",
            "research": "research",
            "fitness": "fitness",
            "verification": "verification",
            "hitl": "hitl",
            "persist": "persist",
            END: END,
        },
    )
    graph.add_edge("user", "supervisor")
    graph.add_edge("planning", "supervisor")
    graph.add_edge("research", "supervisor")
    graph.add_edge("fitness", "verification")
    graph.add_edge("verification", "supervisor")
    graph.add_edge("hitl", "supervisor")
    graph.add_edge("persist", END)

    # See RunOrchestrator.__init__ (graph/service.py) for why this falls back to
    # an in-memory checkpointer rather than Postgres: production always passes
    # one in explicitly via api/deps.py:get_orchestrator.
    saver = checkpointer or MemorySaver()
    return graph.compile(
        checkpointer=saver,
        interrupt_before=["hitl"],
    )
