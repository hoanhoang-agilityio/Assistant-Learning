"""State of the general-QA agent.

A knowledge question must not be able to mutate the plan. That is enforced
structurally — this state has no ``plan``, ``draft_plan`` or ``macros`` field to
write to. The plan reaches the agent as ``plan_context``, a rendered read-only
string, so there is nothing for the model to write back even by mistake.
"""

from langchain.agents.middleware import AgentState


class QAState(AgentState):
    """Working state of the QA agent.

    ``messages`` comes from ``AgentState``, along with the two private keys the
    agent runtime needs.
    """

    plan_context: str
    # All three are rendered by the parent and passed down. This agent must not
    # search for itself: five agents each searching would multiply the cost and
    # let them reason over different retrievals of the same history.
    #
    # `semantic_context` is what is known about the user right now, including
    # anything they said this turn; `episodic_context` is dated accounts of
    # earlier conversations. Separate fields because a model given them as one
    # list will report a thing that was true in March as true today.
    semantic_context: str
    episodic_context: str
