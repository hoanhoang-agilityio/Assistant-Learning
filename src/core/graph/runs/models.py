"""Serializable run DTOs shared by the orchestrator and the HTTP layer.

These live in core (not api/) on purpose. RunOrchestrator *constructs* RunStatus
in six methods, so moving the dataclasses into api/ would force core to import
from api -- inverting the core -> api dependency direction that this codebase
otherwise keeps clean. Giving them their own module inside core gets them out of
the god file without introducing that violation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.agents.state import ApprovalStatus

RunLifecycleStatus = Literal[
    "running", "waiting_hitl", "completed", "failed", "refused", "not_found"
]


class RunNotFoundError(LookupError):
    """Raised when a run id is unknown to the checkpointer."""


@dataclass(frozen=True)
class RunEvent:
    """One item on a run's live event queue -- either a LangGraph node update
    (a raw ``(namespace, {node_name: state_update})`` chunk straight from
    ``graph.stream(stream_mode="updates", subgraphs=True)``, unmodified) or the
    terminal event closing the stream once the run settles.

    This is the single source of progress data for `GET /runs/{run_id}/events`
    (see api/routes/runs.py) -- there is no separate progress-tracking
    abstraction layered on top of LangGraph's own streamed events.
    """

    kind: Literal["node_update", "run_settled"]
    chunk: tuple[tuple[str, ...], dict[str, Any]] | None = None
    status: RunStatus | None = None


@dataclass(frozen=True)
class RunStatus:
    """Serializable run status for API and UI consumers."""

    run_id: str
    thread_id: str
    status: RunLifecycleStatus
    current_node: str
    query: str
    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    verification_passed: bool
    faithfulness_score: float | None
    intent: str | None
    response_mode: str | None
    active_capability: str | None
    final_response: str | None
    final_artifact_path: str | None
    final_plan: str | None
    hitl_type: str | None
    hitl_message: str | None
    refusal_message: str | None
    steps: tuple[str, ...]
    next_nodes: tuple[str, ...]
    error_message: str | None = None
    profile_form: dict[str, Any] | None = None
