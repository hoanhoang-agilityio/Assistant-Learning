from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.graph.checkpointer import create_memory_checkpointer
from core.graph.routing import route_from_supervisor
from core.subgraphs.fitness.graph import invoke_fitness_subgraph
from core.subgraphs.planning.graph import invoke_planning_subgraph
from core.subgraphs.research.graph import invoke_research_subgraph
from core.subgraphs.verification.graph import invoke_verification_subgraph


def planning_node(state: OrchestrationState) -> dict:
    return invoke_planning_subgraph(state)


def research_node(state: OrchestrationState) -> dict:
    return invoke_research_subgraph(state)


def fitness_node(state: OrchestrationState) -> dict:
    return invoke_fitness_subgraph(state)


def verification_node(state: OrchestrationState) -> dict:
    return invoke_verification_subgraph(state)


def hitl_node(state: OrchestrationState) -> dict:
    return {
        "current_node": "hitl",
        "waiting_for_user": False,
        "approval_status": state["approval_status"] or "approved",
    }


def persist_node(state: OrchestrationState) -> dict:
    workspace_path = state["workspace_path"]
    return {
        "current_node": "persist",
        "final_artifact_path": f"{workspace_path}/final/final_plan.md",
    }


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the supervisor-orchestrated LangGraph."""
    graph = StateGraph(OrchestrationState)

    graph.add_node("supervisor", supervisor_node)
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
