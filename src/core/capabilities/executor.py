"""Narrow interface between a capability's graph node and its decision logic.

Every capability (Planning, Research, Fitness, Verification) currently
executes its tools through a deterministic `CapabilityExecutor` implementation.
Swapping any one of them for an LLM-driven ReAct agent later means writing a
new class that satisfies this same `execute(state, ctx) -> CapabilityResult`
signature and passing it to that capability's `configure_*_executor` -- the
graph, dispatcher, contracts, and routing never change.
"""

from __future__ import annotations

from typing import Protocol

from core.agents.execution_context import CapabilityResult, ExecutionContext
from core.agents.state import OrchestrationState


class CapabilityExecutor(Protocol):
    def execute(self, state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult: ...
