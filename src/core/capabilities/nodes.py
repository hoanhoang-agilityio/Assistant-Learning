"""Capability node wrappers for the top-level graph."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from core.agents.state import OrchestrationState
from core.subgraphs.fitness.capability import invoke_fitness_capability
from core.subgraphs.planning.capability import invoke_planning_capability
from core.subgraphs.research.capability import invoke_research_capability
from core.subgraphs.user.graph import invoke_user_subgraph
from core.subgraphs.verification.capability import invoke_verification_capability


def invoke_planning_node(state: OrchestrationState) -> dict:
    return invoke_planning_capability(state)


def invoke_research_node(state: OrchestrationState) -> dict:
    return invoke_research_capability(state)


def invoke_fitness_node(state: OrchestrationState) -> dict:
    return invoke_fitness_capability(state)


def invoke_verification_node(state: OrchestrationState) -> dict:
    return invoke_verification_capability(state)


def invoke_user_node(state: OrchestrationState, config: RunnableConfig) -> dict:
    return invoke_user_subgraph(state, config)
