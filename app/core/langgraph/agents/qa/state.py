"""State for the general-QA agent.

A knowledge question must not be
able to mutate the plan. That is enforced structurally — this state has no
``plan``, ``draft_plan`` or ``macros`` field to write to. The plan reaches the
agent as ``plan_context``, a rendered read-only string, so there is nothing for
a node to write back even by mistake.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class QAState(TypedDict):
    """Working state of the QA subgraph."""

    messages: Annotated[list, add_messages]
    plan_context: str
    # Retrieved once at the root facade and passed down. This agent must not
    # search memory itself: five agents each searching would multiply the cost
    # and let them reason over different retrievals of the same fact.
    long_term_memory: str
    answer: str
