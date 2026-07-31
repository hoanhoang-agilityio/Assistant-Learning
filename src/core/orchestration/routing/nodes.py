"""Capability node wrappers for the top-level graph."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from core.capabilities.fitness.capability import invoke_fitness_capability
from core.capabilities.research.capability import invoke_research_capability
from core.capabilities.user.graph import invoke_user_subgraph
from core.capabilities.verification.capability import invoke_verification_capability
from core.orchestration.state import OrchestrationState


def invoke_research_node(state: OrchestrationState) -> dict:
    return invoke_research_capability(state)


def invoke_fitness_node(state: OrchestrationState) -> dict:
    return invoke_fitness_capability(state)


def invoke_verification_node(state: OrchestrationState) -> dict:
    return invoke_verification_capability(state)


def invoke_user_node(state: OrchestrationState, config: RunnableConfig) -> dict:
    return invoke_user_subgraph(state, config)
