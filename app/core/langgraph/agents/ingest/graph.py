"""Ingest subgraph: parse a pasted plan, then match its names to the catalog."""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.ingest.nodes import parse_plan, resolve_names
from app.core.langgraph.agents.ingest.state import IngestState

AGENT_NAME = "ingest"


def build_ingest_graph() -> CompiledStateGraph:
    """Compile the ingest subgraph.

    Two steps, always in this order: transcribe, then identify. Splitting them
    is what keeps the identification auditable — the model never sees the
    catalog, so it cannot influence which exercise a name resolves to

    Compiled without a checkpointer — the root graph's persists the whole tree.

    Returns:
        The compiled subgraph, named so its spans are identifiable in Langfuse.
    """
    builder = StateGraph(IngestState)
    builder.add_node("parse_plan", parse_plan, destinations=("resolve_names", END))
    builder.add_node("resolve_names", resolve_names, destinations=(END,))
    builder.set_entry_point("parse_plan")
    return builder.compile(name=AGENT_NAME)
