from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.graph.checkpointer import create_memory_checkpointer
from core.graph.routing import route_from_supervisor
from core.hitl.node import invoke_hitl_node
from core.observability.langfuse import supervisor_span_context
from core.observability.tracing import wrap_traced_subgraph_node
from core.persist.node import invoke_persist_node
from core.subgraphs.fitness.graph import invoke_fitness_subgraph
from core.subgraphs.planning.graph import invoke_planning_subgraph
from core.subgraphs.research.graph import invoke_research_subgraph
from core.subgraphs.verification.graph import invoke_verification_subgraph


def traced_supervisor_node(state: OrchestrationState) -> dict:
    with supervisor_span_context(state) as span:
        result = supervisor_node(state)
        if span is not None:
            span.update(output=result)
        return result


planning_node = wrap_traced_subgraph_node("planning", invoke_planning_subgraph)
research_node = wrap_traced_subgraph_node("research", invoke_research_subgraph)
fitness_node = wrap_traced_subgraph_node("fitness", invoke_fitness_subgraph)
verification_node = wrap_traced_subgraph_node("verification", invoke_verification_subgraph)
hitl_node = wrap_traced_subgraph_node("hitl", invoke_hitl_node)
persist_node = wrap_traced_subgraph_node("persist", invoke_persist_node)


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the supervisor-orchestrated LangGraph."""
    graph = StateGraph(OrchestrationState)

    graph.add_node("supervisor", traced_supervisor_node)
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
            "planning": "planning",
            "research": "research",
            "fitness": "fitness",
            "verification": "verification",
            "hitl": "hitl",
            "persist": "persist",
        },
    )
    graph.add_edge("planning", "supervisor")
    graph.add_edge("research", "supervisor")
    graph.add_edge("fitness", "verification")
    graph.add_edge("verification", "supervisor")
    graph.add_edge("hitl", "supervisor")
    graph.add_edge("persist", END)

    saver = checkpointer or create_memory_checkpointer()
    return graph.compile(
        checkpointer=saver,
        interrupt_before=["hitl"],
    )
