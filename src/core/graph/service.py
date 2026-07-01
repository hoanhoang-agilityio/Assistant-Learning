from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from core.agents.state import ApprovalStatus, OrchestrationState
from core.config.settings import get_settings
from core.graph.builder import build_graph
from core.graph.checkpointer import create_memory_checkpointer
from core.graph.run import create_initial_state
from core.observability.langfuse import build_graph_invoke_config, flush_langfuse
from core.profile.labels import format_missing_profile_prompt
from core.rate_limit import (
    AIRateLimiter,
    reset_rate_limit_user_id,
    set_rate_limit_user_id,
)
from core.vfs import VFS

logger = logging.getLogger(__name__)

RunLifecycleStatus = Literal["running", "waiting_hitl", "completed", "failed", "not_found"]


class RunNotFoundError(LookupError):
    """Raised when a run id is unknown to the checkpointer."""


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
    route_decision: str | None
    request_type: str | None
    final_artifact_path: str | None
    final_plan: str | None
    hitl_type: str | None
    hitl_message: str | None
    next_nodes: tuple[str, ...]
    error_message: str | None = None


class RunOrchestrator:
    """Execute and resume orchestration runs via the compiled LangGraph."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        rate_limiter: AIRateLimiter | None = None,
    ) -> None:
        self._checkpointer = checkpointer or create_memory_checkpointer()
        self._graph: CompiledStateGraph = build_graph(checkpointer=self._checkpointer)
        self._rate_limiter = rate_limiter or AIRateLimiter()
        self._lock = threading.Lock()
        self._pending_runs: dict[str, dict[str, Any]] = {}
        self._run_failures: dict[str, dict[str, str]] = {}

    @property
    def graph(self) -> CompiledStateGraph:
        return self._graph

    def create_run(
        self,
        *,
        query: str,
        user_profile: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
    ) -> RunStatus:
        resolved_run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        self._rate_limiter.reserve_request(user_id)
        state = create_initial_state(
            run_id=resolved_run_id,
            thread_id=resolved_run_id,
            query=query,
            user_profile=user_profile,
            constraints=constraints,
            user_id=user_id,
        )
        config = build_graph_invoke_config(state)
        result = self._graph.invoke(state, config)
        flush_langfuse()
        snapshot = self._graph.get_state(config)
        return self._to_status(resolved_run_id, result, snapshot.next)

    def start_run(
        self,
        *,
        query: str,
        user_profile: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
    ) -> RunStatus:
        """Start a run in a background thread and return immediately."""
        resolved_run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        self._rate_limiter.reserve_request(user_id)
        state = create_initial_state(
            run_id=resolved_run_id,
            thread_id=resolved_run_id,
            query=query,
            user_profile=user_profile,
            constraints=constraints,
            user_id=user_id,
        )
        config = build_graph_invoke_config(state)
        with self._lock:
            self._run_failures.pop(resolved_run_id, None)
            self._pending_runs[resolved_run_id] = state
        thread = threading.Thread(
            target=self._execute_create_run,
            args=(state, config, resolved_run_id),
            daemon=True,
            name=f"run-{resolved_run_id}",
        )
        thread.start()
        return self._pending_status(resolved_run_id, state)

    def get_run(self, run_id: str) -> RunStatus:
        with self._lock:
            failure = self._run_failures.get(run_id)
            pending = self._pending_runs.get(run_id)
        if failure is not None:
            return self._failed_status(run_id, failure)
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if snapshot.values:
            return self._to_status(run_id, snapshot.values, snapshot.next)
        if pending is not None:
            return self._pending_status(run_id, pending)
        raise RunNotFoundError(f"Run not found: {run_id}")

    def resume_run(
        self,
        run_id: str,
        *,
        user_response: str,
        approval_status: ApprovalStatus | None = None,
    ) -> RunStatus:
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")
        if snapshot.next != ("hitl",) and not snapshot.values.get("waiting_for_user"):
            raise ValueError("Run is not waiting for HITL input")

        resolved_status = approval_status or _approval_from_response(user_response)
        update: dict[str, Any] = {
            "user_response": user_response,
            "approval_status": resolved_status,
            "waiting_for_user": False,
        }
        missing_fields = snapshot.values.get("user_profile", {}).get("missing_fields", [])
        if missing_fields and resolved_status == "revision_requested":
            update["query"] = f"{snapshot.values.get('query', '')}\n{user_response}".strip()
            cleared_profile = {
                key: value
                for key, value in snapshot.values.get("user_profile", {}).items()
                if key != "missing_fields"
            }
            update["user_profile"] = cleared_profile
        return self.start_resume_run(run_id, update=update)

    def start_resume_run(self, run_id: str, *, update: dict[str, Any]) -> RunStatus:
        """Resume a HITL-paused run in a background thread and return immediately."""
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")
        if snapshot.next != ("hitl",) and not snapshot.values.get("waiting_for_user"):
            raise ValueError("Run is not waiting for HITL input")

        with self._lock:
            self._run_failures.pop(run_id, None)
            self._pending_runs[run_id] = {**snapshot.values, **update}

        thread = threading.Thread(
            target=self._execute_resume_run,
            args=(run_id, update, config),
            daemon=True,
            name=f"resume-{run_id}",
        )
        thread.start()
        resumed_state = {**snapshot.values, **update, "waiting_for_user": False}
        return self._to_status(run_id, resumed_state, ("supervisor",))

    def _execute_resume_run(
        self,
        run_id: str,
        update: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        snapshot = self._graph.get_state(config)
        user_id = str(snapshot.values.get("user_id", ""))
        context_token = set_rate_limit_user_id(user_id or None)
        try:
            self._graph.invoke(Command(update=update), config)
            flush_langfuse()
        except Exception as exc:
            logger.exception("Resume for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        finally:
            reset_rate_limit_user_id(context_token)
            with self._lock:
                self._pending_runs.pop(run_id, None)

    def _execute_create_run(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        run_id: str,
    ) -> None:
        context_token = set_rate_limit_user_id(str(state.get("user_id", "")) or None)
        try:
            self._graph.invoke(state, config)
            flush_langfuse()
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            with self._lock:
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(state.get("query", "")),
                }
        finally:
            reset_rate_limit_user_id(context_token)
            with self._lock:
                self._pending_runs.pop(run_id, None)

    def _pending_status(self, run_id: str, state: dict[str, Any]) -> RunStatus:
        return RunStatus(
            run_id=run_id,
            thread_id=run_id,
            status="running",
            current_node="supervisor",
            query=str(state.get("query", "")),
            waiting_for_user=False,
            approval_status=None,
            verification_passed=False,
            faithfulness_score=None,
            route_decision=None,
            request_type=None,
            final_artifact_path=None,
            final_plan=None,
            hitl_type=None,
            hitl_message=None,
            next_nodes=("supervisor",),
            error_message=None,
        )

    def _failed_status(self, run_id: str, failure: dict[str, str]) -> RunStatus:
        return RunStatus(
            run_id=run_id,
            thread_id=run_id,
            status="failed",
            current_node="supervisor",
            query=failure.get("query", ""),
            waiting_for_user=False,
            approval_status=None,
            verification_passed=False,
            faithfulness_score=None,
            route_decision=None,
            request_type=None,
            final_artifact_path=None,
            final_plan=None,
            hitl_type=None,
            hitl_message=failure.get("error"),
            next_nodes=(),
            error_message=failure.get("error"),
        )

    def _build_config(self, run_id: str) -> dict[str, Any]:
        return build_graph_invoke_config(
            OrchestrationState(
                run_id=run_id,
                thread_id=run_id,
                user_id=get_settings().rate_limit_default_user_id,
                current_node="supervisor",
                query="",
                user_profile={},
                constraints={},
                request_type=None,
                affected_domains=[],
                route_decision=None,
                retry_count=0,
                replan_count=0,
                verification_passed=False,
                faithfulness_score=None,
                waiting_for_user=False,
                approval_status=None,
                user_response=None,
                workspace_path="",
                final_artifact_path=None,
            )
        )

    def _to_status(
        self,
        run_id: str,
        state: dict[str, Any],
        next_nodes: tuple[str, ...],
    ) -> RunStatus:
        lifecycle = _resolve_lifecycle_status(state, next_nodes)
        final_plan = _read_final_plan(state)
        hitl_type, hitl_message = _resolve_hitl_context(state, next_nodes)
        return RunStatus(
            run_id=run_id,
            thread_id=str(state.get("thread_id", run_id)),
            status=lifecycle,
            current_node=_resolve_display_node(state, next_nodes, lifecycle),
            query=str(state.get("query", "")),
            waiting_for_user=bool(state.get("waiting_for_user")),
            approval_status=state.get("approval_status"),
            verification_passed=bool(state.get("verification_passed")),
            faithfulness_score=state.get("faithfulness_score"),
            route_decision=state.get("route_decision"),
            request_type=state.get("request_type"),
            final_artifact_path=state.get("final_artifact_path"),
            final_plan=final_plan,
            hitl_type=hitl_type,
            hitl_message=hitl_message,
            next_nodes=next_nodes,
            error_message=None,
        )


def _resolve_display_node(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
    lifecycle: RunLifecycleStatus,
) -> str:
    """Return the node the UI should show as the active pipeline step.

    While a run is in flight, LangGraph checkpoints only update when a node
    finishes, so ``state["current_node"]`` lags behind the subgraph that is
    actually executing. Prefer ``next_nodes[0]`` in that case.
    """
    if lifecycle == "running" and next_nodes:
        return next_nodes[0]
    return str(state.get("current_node", "supervisor"))


def _resolve_lifecycle_status(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
) -> RunLifecycleStatus:
    if next_nodes == ("hitl",) or (
        state.get("waiting_for_user") and state.get("current_node") != "persist"
    ):
        return "waiting_hitl"
    if state.get("current_node") == "persist" and not next_nodes:
        return "completed"
    if next_nodes:
        return "running"
    if state.get("final_artifact_path"):
        return "completed"
    return "running"


def _approval_from_response(user_response: str) -> ApprovalStatus:
    normalized = user_response.strip().lower()
    if normalized in {"approve", "approved", "yes"}:
        return "approved"
    if normalized in {"reject", "rejected", "no"}:
        return "rejected"
    return "revision_requested"


def _read_final_plan(state: dict[str, Any]) -> str | None:
    workspace_path = state.get("workspace_path")
    if not workspace_path:
        return None
    vfs = VFS.for_run(Path(workspace_path))
    if vfs.exists("final/final_plan.md"):
        return vfs.read("final/final_plan.md")
    if vfs.exists("fitness/final_plan.md"):
        return vfs.read("fitness/final_plan.md")
    return None


def _resolve_hitl_context(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
) -> tuple[str | None, str | None]:
    if next_nodes != ("hitl",) and not state.get("waiting_for_user"):
        return None, None

    workspace_path = state.get("workspace_path")
    if not workspace_path:
        return None, "Waiting for user input."

    missing_fields = state.get("user_profile", {}).get("missing_fields", [])
    if missing_fields:
        return "clarification", format_missing_profile_prompt(missing_fields)

    draft_plan = _read_final_plan(state)
    if draft_plan:
        preview = draft_plan[:500]
        if state.get("verification_passed") or state.get("route_decision") == "COMPLETE":
            return (
                "approval",
                f"Review the draft fitness plan and approve or reject. Preview:\n\n{preview}",
            )
        return (
            "approval",
            "A draft plan is ready for review. Verification did not fully pass, but you can "
            f"approve, reject, or refresh after changes. Preview:\n\n{preview}",
        )

    return "approval", "Waiting for approval or clarification."
