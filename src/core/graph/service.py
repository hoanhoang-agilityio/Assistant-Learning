from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from core.agents.state import ApprovalStatus
from core.graph.builder import build_graph
from core.graph.run import create_initial_state
from core.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    user_revision_to_replan_update,
)
from core.hitl.utils import classify_approval_response
from core.llm.metrics import reset_llm_metrics, write_pipeline_cost_log
from core.observability.langfuse import build_graph_invoke_config, flush_langfuse
from core.profile.labels import format_missing_profile_prompt
from core.rate_limit import (
    AIRateLimiter,
    reset_rate_limit_user_id,
    set_rate_limit_user_id,
)
from core.subgraphs.planning.utils import persist_revision_feedback
from core.vfs import VFS

logger = logging.getLogger(__name__)

RunLifecycleStatus = Literal[
    "running", "waiting_hitl", "completed", "failed", "refused", "not_found"
]


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
    refusal_message: str | None
    steps: tuple[str, ...]
    pending_tool: str | None
    next_nodes: tuple[str, ...]
    error_message: str | None = None


class RunOrchestrator:
    """Execute and resume orchestration runs via the compiled LangGraph."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        rate_limiter: AIRateLimiter | None = None,
    ) -> None:
        # Production wiring (Postgres-backed, per settings.use_postgres_checkpointer)
        # lives in api/deps.py:get_orchestrator, the only call site that constructs
        # this class for the running API. The in-memory fallback below is
        # intentional for tests and scripts (e.g. ragas_benchmark.py) that build
        # subgraphs/orchestrators directly without going through deps.py.
        self._checkpointer = checkpointer or MemorySaver()
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
        reset_llm_metrics()
        state = create_initial_state(
            run_id=resolved_run_id,
            thread_id=resolved_run_id,
            query=query,
            user_profile=user_profile,
            constraints=constraints,
            user_id=user_id,
        )
        config = build_graph_invoke_config(state)
        self._graph.invoke(state, config)
        flush_langfuse()
        snapshot = self._graph.get_state(config)
        self._maybe_write_token_cost_log(snapshot.values, snapshot.next)
        return self._to_status(
            resolved_run_id,
            snapshot.values,
            snapshot.next,
            interrupts=_collect_interrupts(snapshot),
        )

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
        reset_llm_metrics()
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
            return self._to_status(
                run_id, snapshot.values, snapshot.next, interrupts=_collect_interrupts(snapshot)
            )
        if pending is not None:
            return self._pending_status(run_id, pending)
        raise RunNotFoundError(f"Run not found: {run_id}")

    def resume_run(
        self,
        run_id: str,
        *,
        user_response: str | None = None,
        approval_status: ApprovalStatus | None = None,
        decision_type: Literal["approve", "reject", "revision"] | None = None,
        message: str | None = None,
        pending_tool: str | None = None,
        approved_tools: list[str] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> RunStatus:
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")

        if snapshot.next == ("user",):
            if form_data is None:
                raise ValueError("form_data is required to resume the profile form")
            return self.start_profile_form_resume(run_id, form_data=form_data)

        if snapshot.next != ("hitl",) and not snapshot.values.get("waiting_for_user"):
            raise ValueError("Run is not waiting for HITL input")

        if decision_type is not None:
            decision = create_approval_decision(
                decision_type,
                message,
                pending_tool=pending_tool or snapshot.values.get("pending_tool"),
                approved_tools=approved_tools or snapshot.values.get("approved_tools"),
            )
            update = decision_to_resume_update(
                decision,
                replan_count=int(snapshot.values.get("replan_count") or 0),
            )
        else:
            if not user_response:
                raise ValueError("user_response or decision_type is required")
            resolved_status = approval_status or classify_approval_response(
                user_response, strict=True
            )
            update = {
                "user_response": user_response,
                "approval_status": resolved_status,
                "waiting_for_user": False,
            }
            if pending_tool and resolved_status == "approved":
                merged_tools = list(snapshot.values.get("approved_tools") or [])
                if pending_tool not in merged_tools:
                    merged_tools.append(pending_tool)
                update["approved_tools"] = merged_tools
                update["pending_tool"] = None

        resolved_status = update.get("approval_status")
        if resolved_status == "revision_requested":
            # Profile-relevant revisions are no longer reconstructed here -- the routing
            # guard (route_from_supervisor) sends REPLAN runs back into the User subgraph
            # when profile_complete/profile_valid is False, and the User subgraph's own
            # extract/validate loop decides whether that revision text actually touched the
            # profile (looping into its form) or can pass straight through.
            feedback = update.get("user_response") or message or ""
            update.update(user_revision_to_replan_update(feedback))
            update["profile_complete"] = False
            update["profile_valid"] = False
            workspace_path = snapshot.values.get("workspace_path")
            if workspace_path and update.get("revision_feedback"):
                persist_revision_feedback(str(workspace_path), str(update["revision_feedback"]))
        return self.start_resume_run(run_id, update=update)

    def start_profile_form_resume(self, run_id: str, *, form_data: dict[str, Any]) -> RunStatus:
        """Resume a run paused at the profile form (dynamic `interrupt()`) with submitted data.

        Distinct from `start_resume_run` because the User subgraph pauses via `interrupt()`
        rather than the top-level `interrupt_before=["hitl"]` boundary, so resuming it means
        `Command(resume=form_data)`, not `Command(update=...)`.
        """
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")
        if snapshot.next != ("user",):
            raise ValueError("Run is not waiting for the profile form")

        with self._lock:
            self._run_failures.pop(run_id, None)
            self._pending_runs[run_id] = snapshot.values

        thread = threading.Thread(
            target=self._execute_profile_form_resume,
            args=(run_id, form_data, config),
            daemon=True,
            name=f"profile-form-resume-{run_id}",
        )
        thread.start()
        return self._to_status(run_id, snapshot.values, ("user",))

    def _execute_profile_form_resume(
        self,
        run_id: str,
        form_data: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        snapshot = self._graph.get_state(config)
        user_id = str(snapshot.values.get("user_id", ""))
        context_token = set_rate_limit_user_id(user_id or None)
        try:
            self._graph.invoke(Command(resume=form_data), config)
            flush_langfuse()
        except Exception as exc:
            logger.exception("Profile form resume for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        finally:
            snapshot = self._graph.get_state(config)
            with self._lock:
                failed = run_id in self._run_failures
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
            reset_rate_limit_user_id(context_token)
            with self._lock:
                self._pending_runs.pop(run_id, None)

    def continue_run(self, run_id: str, *, message: str) -> RunStatus:
        """Replan from an existing conversation when the user changes plan preferences."""
        feedback = message.strip()
        if not feedback:
            raise ValueError("message is required")

        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")

        lifecycle = _resolve_lifecycle_status(snapshot.values, snapshot.next)
        if lifecycle not in {"completed", "waiting_hitl"}:
            raise ValueError("Run cannot accept plan changes in its current state")

        self._rate_limiter.reserve_request(str(snapshot.values.get("user_id", "")) or None)
        update = user_revision_to_replan_update(feedback)
        # The routing guard (route_from_supervisor) re-enters the User subgraph for this
        # REPLAN since profile_complete/profile_valid is now False -- see resume_run's
        # revision_requested branch for the same pattern.
        update["profile_complete"] = False
        update["profile_valid"] = False
        update["current_node"] = "hitl"
        update["final_artifact_path"] = None
        workspace_path = snapshot.values.get("workspace_path")
        if workspace_path:
            persist_revision_feedback(str(workspace_path), feedback)

        if snapshot.next == ("hitl",) or snapshot.values.get("waiting_for_user"):
            return self.start_resume_run(run_id, update=update)
        return self.start_continue_run(run_id, update=update, config=config)

    def start_continue_run(
        self,
        run_id: str,
        *,
        update: dict[str, Any],
        config: dict[str, Any],
    ) -> RunStatus:
        """Resume a completed run into a replan without requiring an active HITL interrupt."""
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")

        with self._lock:
            self._run_failures.pop(run_id, None)
            self._pending_runs[run_id] = {**snapshot.values, **update}

        thread = threading.Thread(
            target=self._execute_continue_run,
            args=(run_id, update, config),
            daemon=True,
            name=f"continue-{run_id}",
        )
        thread.start()
        resumed_state = {**snapshot.values, **update, "waiting_for_user": False}
        return self._to_status(run_id, resumed_state, ("supervisor",))

    def _execute_continue_run(
        self,
        run_id: str,
        update: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        snapshot = self._graph.get_state(config)
        user_id = str(snapshot.values.get("user_id", ""))
        context_token = set_rate_limit_user_id(user_id or None)
        try:
            self._graph.invoke(Command(update=update, goto="supervisor"), config)
            flush_langfuse()
        except Exception as exc:
            logger.exception("Continue for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        finally:
            snapshot = self._graph.get_state(config)
            with self._lock:
                failed = run_id in self._run_failures
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
            reset_rate_limit_user_id(context_token)
            with self._lock:
                self._pending_runs.pop(run_id, None)

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
            snapshot = self._graph.get_state(config)
            with self._lock:
                failed = run_id in self._run_failures
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
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
            snapshot = self._graph.get_state(config)
            with self._lock:
                failed = run_id in self._run_failures
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
            reset_rate_limit_user_id(context_token)
            with self._lock:
                self._pending_runs.pop(run_id, None)

    def _maybe_write_token_cost_log(
        self,
        state: dict[str, Any],
        next_nodes: tuple[str, ...],
        *,
        failed: bool = False,
    ) -> None:
        if not state:
            return
        if not failed:
            lifecycle = _resolve_lifecycle_status(state, next_nodes)
            if lifecycle != "completed":
                return
        workspace_path = str(state.get("workspace_path", ""))
        run_id = str(state.get("run_id", ""))
        if not workspace_path or not run_id:
            return
        write_pipeline_cost_log(workspace_path, run_id=run_id)

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
            refusal_message=None,
            steps=(),
            pending_tool=None,
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
            refusal_message=None,
            steps=(),
            pending_tool=None,
            next_nodes=(),
            error_message=failure.get("error"),
        )

    def _build_config(self, run_id: str) -> dict[str, Any]:
        # build_graph_invoke_config only reads state["thread_id"]/state["run_id"] (both equal
        # to run_id for every _build_config caller), so a full OrchestrationState literal isn't
        # needed here -- mirrors the narrowing precedent in agents/supervisor.py.
        return build_graph_invoke_config(
            {"run_id": run_id, "thread_id": run_id}  # type: ignore[typeddict-item]
        )

    def _to_status(
        self,
        run_id: str,
        state: dict[str, Any],
        next_nodes: tuple[str, ...],
        *,
        interrupts: tuple[Any, ...] = (),
    ) -> RunStatus:
        lifecycle = _resolve_lifecycle_status(state, next_nodes, interrupts)
        final_plan = _read_final_plan(state)
        hitl_type, hitl_message = _resolve_hitl_context(state, next_nodes, interrupts)
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
            refusal_message=state.get("refusal_message"),
            steps=tuple(state.get("steps") or ()),
            pending_tool=state.get("pending_tool"),
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
    interrupts: tuple[Any, ...] = (),
) -> RunLifecycleStatus:
    if state.get("route_decision") == "REFUSED":
        return "refused"
    if state.get("approval_status") == "rejected" and not next_nodes:
        return "completed"
    if state.get("approval_status") == "approved" and state.get("final_artifact_path"):
        return "completed"
    if (
        state.get("approval_status") == "approved"
        and not next_nodes
        and state.get("current_node") == "persist"
    ):
        return "completed"
    # `next_nodes == ("user",)` is ambiguous on its own: LangGraph reports it both when the
    # User subgraph is genuinely paused mid-interrupt() *and*, transiently, the instant
    # before "user" starts executing (it's a regular node, not a static interrupt_before
    # gate like "hitl"). Only a populated `interrupts` list means it's durably paused.
    if (
        next_nodes == ("hitl",)
        or (next_nodes == ("user",) and interrupts)
        or (state.get("waiting_for_user") and state.get("current_node") != "persist")
    ):
        return "waiting_hitl"
    if state.get("current_node") == "persist" and not next_nodes:
        return "completed"
    if next_nodes:
        return "running"
    if state.get("final_artifact_path"):
        return "completed"
    return "running"


def _collect_interrupts(snapshot: Any) -> tuple[Any, ...]:
    """Flatten every pending interrupt across a graph snapshot's tasks."""
    return tuple(interrupt for task in snapshot.tasks for interrupt in (task.interrupts or ()))


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


def _extract_profile_form_payload(interrupts: tuple[Any, ...]) -> dict[str, Any] | None:
    for item in interrupts:
        value = getattr(item, "value", None)
        if isinstance(value, dict) and value.get("type") == "profile_form":
            return value
    return None


def _resolve_hitl_context(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
    interrupts: tuple[Any, ...] = (),
) -> tuple[str | None, str | None]:
    if next_nodes == ("user",):
        # Same ambiguity as _resolve_lifecycle_status: next_nodes == ("user",) alone
        # doesn't mean paused -- it can also be a transient "about to run" read, since
        # "user" is a regular node, not a static interrupt_before gate. Only report
        # "profile_form" when there's an actual recorded interrupt.
        payload = _extract_profile_form_payload(interrupts)
        if payload is not None:
            missing_fields = payload.get("missing_fields") or []
            if missing_fields:
                return "profile_form", format_missing_profile_prompt(missing_fields)
            return "profile_form", "Please review and submit your profile."
        return None, None

    if state.get("approval_status") in {"rejected", "approved"}:
        return None, None
    if next_nodes != ("hitl",) and not state.get("waiting_for_user"):
        return None, None

    workspace_path = state.get("workspace_path")
    if not workspace_path:
        return None, "Waiting for user input."

    draft_plan = _read_final_plan(state)
    if draft_plan:
        preview = draft_plan[:500]
        if state.get("verification_passed") or state.get("route_decision") == "COMPLETE":
            return (
                "approval",
                f"Review the draft fitness plan. Approve to save, or reject with feedback to replan.\n\n{preview}",
            )
        return (
            "approval",
            "A draft plan is ready for review. Verification did not fully pass, but you can "
            f"approve, reject, or refresh after changes. Preview:\n\n{preview}",
        )

    return "approval", "Waiting for approval or clarification."
