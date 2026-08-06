"""Planning subgraph: template → candidates → choice → assembled plan."""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.planning.nodes import (
    assemble_plan,
    choose_exercises,
    filter_candidates,
    select_template,
)
from app.core.langgraph.agents.planning.state import PlanningState

AGENT_NAME = "planning"


def build_planning_graph() -> CompiledStateGraph:
    """Compile the planning subgraph.

    A fixed pipeline, not a supervisor: the four steps always run in this order
    and none may be skipped, so the sequence is edges rather than a model's
    repeated decision.

    Compiled without a checkpointer — the root graph's persists the whole tree.

    Returns:
        The compiled subgraph, named so its spans are identifiable in Langfuse.
    """
    builder = StateGraph(PlanningState)
    builder.add_node("select_template", select_template, destinations=("filter_candidates", END))
    builder.add_node("filter_candidates", filter_candidates, destinations=("choose_exercises", END))
    builder.add_node("choose_exercises", choose_exercises, destinations=("assemble_plan",))
    builder.add_node("assemble_plan", assemble_plan, destinations=(END,))
    builder.set_entry_point("select_template")
    return builder.compile(name=AGENT_NAME)
