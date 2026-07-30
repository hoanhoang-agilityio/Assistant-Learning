from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.adapters.observability.langfuse import supervisor_span_context
from core.adapters.observability.tracing import wrap_traced_subgraph_node
from core.capabilities.planning.node import invoke_planning_node
from core.capabilities.wrapper import append_pipeline_steps
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.agents.supervisor import supervisor_node
from core.orchestration.graph.routing import route_from_supervisor
from core.orchestration.hitl.node import invoke_hitl_node
from core.orchestration.persist.node import invoke_persist_node
from core.orchestration.routing.nodes import (
    invoke_fitness_node,
    invoke_research_node,
    invoke_user_node,
    invoke_verification_node,
)
from core.orchestration.routing.registry import capability_node_map


def traced_supervisor_node(state: OrchestrationState) -> dict:
    with supervisor_span_context(state) as span:
        result = supervisor_node(state)
        merged = {
            **result,
            "steps": append_pipeline_steps(state, "supervisor", ["classify"]),
        }
        if span is not None:
            span.update(output=merged)
        return merged


planning_node = wrap_traced_subgraph_node("planning", invoke_planning_node)
research_node = wrap_traced_subgraph_node("research", invoke_research_node)
fitness_node = wrap_traced_subgraph_node("fitness", invoke_fitness_node)
verification_node = wrap_traced_subgraph_node("verification", invoke_verification_node)
hitl_node = wrap_traced_subgraph_node("hitl", invoke_hitl_node)
persist_node = wrap_traced_subgraph_node("persist", invoke_persist_node)
user_node = wrap_traced_subgraph_node("user", invoke_user_node, needs_config=True)


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the Supervisor-routed LangGraph.

    The Supervisor is the single routing authority (see docs/reports plan): every
    capability returns control to "supervisor", which proposes the next hop via an
    LLM Router Judge and enforces deterministic business rules via the Policy
    Engine (both inside `supervisor_node`) before the graph's one conditional edge
    routes anywhere. There is no separate dispatcher node.
    """
    graph = StateGraph(OrchestrationState)

    graph.add_node("supervisor", traced_supervisor_node)
    graph.add_node("user", user_node)
    graph.add_node("planning", planning_node)
    graph.add_node("research", research_node)
    graph.add_node("fitness", fitness_node)
    graph.add_node("verification", verification_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("persist", persist_node)

    targets = {**capability_node_map(), END: END}

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor, targets)

    for node in ("user", "planning", "research", "fitness", "verification", "hitl"):
        graph.add_edge(node, "supervisor")
    graph.add_edge("persist", END)

    saver = checkpointer or MemorySaver()
    return graph.compile(
        checkpointer=saver,
        interrupt_before=["hitl"],
    )
