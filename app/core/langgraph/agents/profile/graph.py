"""Profile subgraph: load → extract → check required."""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.langgraph.agents.profile.nodes import (
    check_required,
    extract_profile,
    load_profile,
)
from app.core.langgraph.agents.profile.state import ProfileState

AGENT_NAME = "profile"


def build_profile_graph() -> CompiledStateGraph:
    """Compile the profile subgraph.

    A fixed three-step pipeline. None of the steps is optional, so the order is
    edges rather than anything a model chooses.

    Compiled without a checkpointer — the root graph's persists the whole tree.

    Returns:
        The compiled subgraph, named so its spans are identifiable in Langfuse.
    """
    builder = StateGraph(ProfileState)
    builder.add_node("load_profile", load_profile, destinations=("extract_profile",))
    builder.add_node("extract_profile", extract_profile, destinations=("check_required",))
    builder.add_node("check_required", check_required, destinations=(END,))
    builder.set_entry_point("load_profile")
    return builder.compile(name=AGENT_NAME)
