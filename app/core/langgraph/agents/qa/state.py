"""State of the general-QA agent."""

from langchain.agents.middleware import AgentState


class QAState(AgentState):
    """Working state of the QA agent."""

    plan_context: str
    episodic_context: str
    profile: dict
