"""General-QA subgraph."""

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from app.core.langgraph.agents.qa.nodes import answer_qa, tool_call
from app.core.langgraph.agents.qa.state import QAState

AGENT_NAME = "qa"


def build_qa_graph() -> CompiledStateGraph:
    """Compile the general-QA subgraph.

    Compiled without a checkpointer on purpose: the root graph's checkpointer
    persists the whole tree, and a second one would write a competing history.

    Returns:
        The compiled subgraph, named so its spans are identifiable in Langfuse.
    """
    builder = StateGraph(QAState)
    builder.add_node("answer_qa", answer_qa, destinations=("tool_call", "__end__"))
    builder.add_node(
        "tool_call",
        tool_call,
        destinations=("answer_qa",),
        retry_policy=RetryPolicy(max_attempts=3),
    )
    builder.set_entry_point("answer_qa")
    return builder.compile(name=AGENT_NAME)
