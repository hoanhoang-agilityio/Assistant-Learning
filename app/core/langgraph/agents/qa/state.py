"""State of the general-QA agent.

A knowledge question must not be able to mutate the plan. That is enforced
structurally — this state has no ``plan``, ``draft_plan`` or ``macros`` field to
write to. The plan reaches the agent as ``plan_context``, a rendered read-only
string, so there is nothing for the model to write back even by mistake
(``docs/workflow.md`` §1.3, §9.4).
"""

from langchain.agents.middleware import AgentState


class QAState(AgentState):
    """Working state of the QA agent.

    ``messages`` comes from ``AgentState``, along with the two private keys the
    agent runtime needs.
    """

    plan_context: str
    # Retrieved once at the root facade and passed down. This agent must not
    # search memory itself: five agents each searching would multiply the cost
    # and let them reason over different retrievals of the same fact.
    long_term_memory: str
