"""Run orchestration: invoking, resuming and streaming graph runs.

Two groups have been extracted from this module into ``core.orchestration.graph.runs``:

* ``runs/models.py``     -- the RunEvent/RunStatus DTOs and RunNotFoundError
* ``runs/projection.py`` -- the pure checkpoint -> status projection helpers

Both are re-exported below, so ``from core.orchestration.graph.service import RunStatus`` and
friends keep working.

Three further splits were considered and deliberately **not** made, because each
would relocate coupling rather than remove it:

1. Moving the DTOs into ``api/``. RunOrchestrator constructs RunStatus in six
   methods, so core would have to import from api -- inverting the core -> api
   direction this codebase otherwise keeps clean. They live in ``runs/models.py``
   instead: out of this file, same dependency direction.

2. A separate ``runs/store.py`` for the Postgres methods. _mark_run_tracked,
   _sync_run_tracked, _claim_resume and _persist_run_history are thin wrappers
   over injected stores, but reconcile_orphaned_runs also reads graph
   checkpoints and _sync_run_tracked inspects a LangGraph snapshot -- so the
   extracted class would need the graph injected too, reproducing the coupling
   one level down.

3. A ``runs/status.py`` owning _to_status/_pending_status/_failed_status. These
   are not pure projections: they read self._pending_runs and self._run_failures,
   mutable per-instance state that would have to move with them.

2 and 3 are worth revisiting once RunOrchestrator's mutable state
(_pending_runs, _run_failures, _run_event_queues, _active_resumes) is itself
addressed; splitting the methods before the state they share is what would make
the change risky rather than mechanical.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from core.adapters.db.idempotency_store import IdempotencyStore
from core.adapters.db.run_history_store import (
    InMemoryRunHistoryStore,
    RunHistoryStore,
    RunSummary,
)
from core.adapters.db.run_tracker import RunTracker
from core.adapters.llm.metrics import reset_llm_metrics, write_pipeline_cost_log
from core.adapters.observability.langfuse import build_graph_invoke_config, flush_langfuse
from core.adapters.rate_limit import (
    AIRateLimiter,
    reset_rate_limit_user_id,
    set_rate_limit_user_id,
)
from core.adapters.vfs import VFS
from core.adapters.vfs.layout import PLAN_SUBMITTED_TEXT
from core.config.settings import get_settings
from core.orchestration.graph.builder import build_graph
from core.orchestration.graph.run import create_initial_state
from core.orchestration.graph.runs.models import (
    RunEvent,
    RunLifecycleStatus,
    RunNotFoundError,
    RunStatus,
)
from core.orchestration.graph.runs.projection import (
    _collect_interrupts,
    _extract_profile_form_payload,
    _read_final_plan,
    _resolve_display_node,
    _resolve_hitl_context,
    _resolve_lifecycle_status,
)
from core.orchestration.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
    user_revision_to_replan_update,
)
from core.orchestration.hitl.utils import classify_approval_response
from core.orchestration.state import ApprovalStatus
from core.shared.planning.utils import persist_revision_feedback

logger = logging.getLogger(__name__)


@contextmanager
def best_effort(operation: str, *, run_id: str) -> Iterator[None]:
    """Run a non-business-critical step -- an observability flush, a metrics/
    cost-log write, in-memory bookkeeping -- without letting its failure
    change a run's already-recorded outcome.

    Every call site wrapping this must run strictly *after* the run's
    success/failure has already been decided (self._run_failures populated or
    not); never wrap the code that decides that outcome itself, or a flaky
    cleanup step could turn a genuinely successful run into a falsely
    reported failure -- exactly the bug this helper exists to close.
    """
    try:
        yield
    except Exception:
        logger.warning("best_effort step %r failed for run %s", operation, run_id, exc_info=True)


class RunOrchestrator:
    """Execute and resume orchestration runs via the compiled LangGraph."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
        rate_limiter: AIRateLimiter | None = None,
        run_tracker: RunTracker | None = None,
        idempotency_store: IdempotencyStore | None = None,
        run_history_store: RunHistoryStore | InMemoryRunHistoryStore | None = None,
    ) -> None:
        # Production wiring (Postgres-backed, per settings.use_postgres_checkpointer)
        # lives in api/deps.py:get_orchestrator, the only call site that constructs
        # this class for the running API. The in-memory fallback below is
        # intentional for tests and scripts (e.g. ragas_benchmark.py) that build
        # subgraphs/orchestrators directly without going through deps.py.
        self._checkpointer = checkpointer or MemorySaver()
        self._graph: CompiledStateGraph = build_graph(checkpointer=self._checkpointer)
        self._rate_limiter = rate_limiter or AIRateLimiter()
        # Orphan reconciliation needs a record of "in-flight" that survives a
        # process restart; MemorySaver-backed orchestrators (tests, scripts)
        # have no such durability to reconcile against, so run_tracker is None
        # there and every tracking/reconciliation call below becomes a no-op.
        self._run_tracker = run_tracker
        # Same reasoning: idempotency needs a record that survives a restart
        # and is visible to every replica, so it's a no-op without Postgres.
        self._idempotency_store = idempotency_store
        self._run_history_store = run_history_store or InMemoryRunHistoryStore()
        self._lock = threading.Lock()
        # One long-lived pool backs every _stream_with_timeout() call for this
        # orchestrator's lifetime (default sizing: min(32, cpu_count + 4), so it
        # never becomes a de facto concurrency cap on in-flight runs).
        self._invoke_executor = ThreadPoolExecutor(thread_name_prefix="graph-invoke")
        self._pending_runs: dict[str, dict[str, Any]] = {}
        self._run_failures: dict[str, dict[str, str]] = {}
        # One queue per currently-executing run, feeding GET /runs/{run_id}/events
        # (see api/routes/runs.py). Opened at the start of each _execute_*
        # background method and closed (after one final RunEvent(kind="run_settled",
        # ...) is pushed) once that method's own cleanup has fully run -- an SSE
        # client that already has a reference to the queue keeps draining it after
        # it's removed from this dict, so closing here never drops the terminal
        # event out from under an active connection.
        self._run_event_queues: dict[str, queue.Queue[RunEvent]] = {}
        # Guards the window between reading a run's pre-resume snapshot and the
        # background thread that invokes the graph against it -- without this,
        # two near-simultaneous resume/continue calls both read the same
        # "waiting" snapshot and both invoke the graph concurrently against the
        # same checkpointer thread (double-click, client retry, or a deliberate
        # double-submit). Only one resume/continue may be in flight per run_id;
        # the second is rejected (ValueError, mapped to HTTP 409 by the API
        # layer) rather than racing through.
        self._active_resumes: set[str] = set()

    @property
    def graph(self) -> CompiledStateGraph:
        return self._graph

    def _acquire_resume_guard(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._active_resumes:
                raise ValueError(f"Run {run_id} already has a resume/continue in progress")
            self._active_resumes.add(run_id)

    def _release_resume_guard(self, run_id: str) -> None:
        with self._lock:
            self._active_resumes.discard(run_id)

    def _open_event_stream(self, run_id: str) -> None:
        with self._lock:
            self._run_event_queues[run_id] = queue.Queue()

    def get_event_queue(self, run_id: str) -> queue.Queue[RunEvent] | None:
        """Return run_id's live event queue, or None if it isn't currently executing.

        Read by the SSE endpoint (api/routes/runs.py) -- a None result means the
        run is settled/paused already, so the endpoint should fall back to
        get_run()'s current snapshot instead of waiting on a stream.
        """
        with self._lock:
            return self._run_event_queues.get(run_id)

    def _close_event_stream(self, run_id: str, *, final_status: RunStatus) -> None:
        with self._lock:
            event_queue = self._run_event_queues.pop(run_id, None)
        if event_queue is not None:
            event_queue.put(RunEvent(kind="run_settled", status=final_status))
        with best_effort("persist_run_history", run_id=run_id):
            self._persist_run_history(run_id)

    def _stream_with_timeout(
        self,
        input_data: Any,
        config: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> None:
        """Run self._graph.stream(..., stream_mode="updates", subgraphs=True) under
        a wall-clock deadline, publishing each yielded chunk to run_id's live event
        queue (opened via _open_event_stream) as it arrives.

        Replaces the old single blocking self._graph.invoke() call: every graph
        execution call site in this class goes through here so (a) a hung node (an
        LLM/Tavily call that ignores its own timeout, or a stuck subgraph) can
        never leave a run at "running" forever -- the same guarantee as before,
        now enforced across the stream's iteration instead of around one blocking
        call -- and (b) GET /runs/{run_id}/events (see api/routes/runs.py) can
        observe each node's completion in real time instead of only learning about
        it once the whole run settles. subgraphs=True is what makes LangGraph
        surface a subgraph's *internal* node completions (e.g. "research_agent"
        inside the research subgraph), not just the wrapping "research" node --
        verified empirically against this codebase's actual subgraphs before this
        change; it requires no changes to the subgraphs themselves.

        concurrent.futures cannot forcibly stop a running thread: on timeout, the
        underlying stream may keep executing on self._invoke_executor in the
        background after this raises. That's an accepted limitation, not a bug --
        the goal here is an honest, visible run status, not reclaiming the thread.
        """
        settings = get_settings()
        deadline = time.monotonic() + settings.run_execution_timeout_seconds
        chunk_queue: queue.Queue[Any] = queue.Queue()
        done = object()

        def _drain_stream() -> None:
            try:
                for chunk in self._graph.stream(
                    input_data, config, stream_mode="updates", subgraphs=True
                ):
                    chunk_queue.put(chunk)
            except BaseException as exc:  # noqa: BLE001 -- re-raised on the caller's thread below
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(done)

        self._invoke_executor.submit(_drain_stream)
        timeout_message = (
            f"Graph execution did not finish within "
            f"{settings.run_execution_timeout_seconds:.0f} seconds"
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(timeout_message)
            try:
                item = chunk_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(timeout_message) from exc
            if item is done:
                return
            if isinstance(item, BaseException):
                raise item
            if run_id is not None:
                self._publish_chunk(run_id, item)

    def _publish_chunk(self, run_id: str, chunk: tuple[tuple[str, ...], dict[str, Any]]) -> None:
        with self._lock:
            event_queue = self._run_event_queues.get(run_id)
        if event_queue is not None:
            event_queue.put(RunEvent(kind="node_update", chunk=chunk))

    def _mark_run_tracked(self, run_id: str, *, query: str) -> None:
        """Record that run_id's background execution has started, if tracking is on."""
        if self._run_tracker is not None:
            self._run_tracker.mark_running(run_id, query=query)

    def _clear_run_tracked(self, run_id: str) -> None:
        """Remove run_id's tracking row once its background execution has settled."""
        if self._run_tracker is not None:
            self._run_tracker.clear(run_id)

    def _sync_run_tracked(self, run_id: str, snapshot: Any, *, failed: bool) -> None:
        """Reconcile run_id's tracking row with how its execution actually settled.

        A run that paused for HITL/profile-form input is kept as
        'waiting_hitl' (resumable, guarded by claim_resume) rather than
        cleared -- everything else (completed, refused, or already recorded
        in _run_failures) clears the row like before.
        """
        if failed:
            self._clear_run_tracked(run_id)
            return
        lifecycle = _resolve_lifecycle_status(
            snapshot.values, snapshot.next, _collect_interrupts(snapshot)
        )
        if lifecycle == "waiting_hitl" and self._run_tracker is not None:
            self._run_tracker.mark_waiting(run_id, query=str(snapshot.values.get("query", "")))
        else:
            self._clear_run_tracked(run_id)

    def _claim_resume(self, run_id: str) -> None:
        """Atomically transition run_id from 'waiting_hitl' to 'running' before
        resuming it, so two concurrent resume attempts -- different worker
        processes/replicas, or a client retry racing the original request --
        can never both execute the same resume.

        No-op (relies entirely on the existing in-memory _active_resumes
        guard, which only protects a single process) when run_tracker isn't
        configured -- e.g. MemorySaver-backed test/script orchestrators.

        Raises ValueError -- mapped to 409 Conflict by the API layer, the
        same as every other "run is not in a resumable state" check in this
        class -- when the claim fails.
        """
        if self._run_tracker is None:
            return
        if not self._run_tracker.claim_resume(run_id):
            raise ValueError(f"Run {run_id} has already been resumed")

    def reconcile_orphaned_runs(self) -> int:
        """Mark every run still 'running' past the staleness window as failed.

        Call at process startup (to recover work orphaned by a crash or
        restart of a *previous* process) and periodically while running (to
        recover a run whose own background thread died without reaching its
        except/finally handlers, e.g. a hard interpreter-level fault). No
        automatic retry: an orphaned run is marked failed once and stays
        failed -- resubmitting the request is left to the caller.

        No-op when run_tracker wasn't configured (MemorySaver-backed
        orchestrators have no restart-durable record to reconcile against).
        Returns the number of runs reconciled.
        """
        if self._run_tracker is None:
            return 0
        settings = get_settings()
        orphaned = self._run_tracker.reconcile_orphaned_runs(
            stale_after_seconds=settings.run_execution_timeout_seconds
        )
        if not orphaned:
            return 0
        with self._lock:
            for run_id, query in orphaned:
                self._run_failures[run_id] = {
                    "error": "Run orphaned: the process executing it stopped responding",
                    "error_class": "orphaned",
                    "query": query,
                }
                self._pending_runs.pop(run_id, None)
        logger.warning("Reconciled %d orphaned run(s): %s", len(orphaned), [r for r, _ in orphaned])
        for run_id, _query in orphaned:
            with best_effort("persist_run_history", run_id=run_id):
                self._persist_run_history(run_id)
        return len(orphaned)

    def list_runs(self, user_id: str, *, limit: int = 50) -> list[RunSummary]:
        """Return recent runs for a user, newest first."""
        resolved_user_id = (user_id or "").strip() or get_settings().rate_limit_default_user_id
        return self._run_history_store.list_by_user(resolved_user_id, limit=limit)

    def list_recent_completed(self, *, since: datetime, limit: int = 50) -> list[RunSummary]:
        """All users' completed runs updated since `since`, oldest first.

        Used by core.evaluation.shadow_eval's periodic sweep to find runs
        eligible for shadow faithfulness scoring -- unlike list_runs, not
        scoped to one user_id.
        """
        return self._run_history_store.list_recent_completed(since=since, limit=limit)

    def _resolve_user_id_for_run(self, run_id: str) -> str:
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if snapshot.values:
            user_id = str(snapshot.values.get("user_id", "")).strip()
            if user_id:
                return user_id
        with self._lock:
            pending = self._pending_runs.get(run_id)
        if pending:
            user_id = str(pending.get("user_id", "")).strip()
            if user_id:
                return user_id
        return get_settings().rate_limit_default_user_id

    def _persist_run_history(self, run_id: str) -> None:
        status = self.get_run(run_id)
        user_id = self._resolve_user_id_for_run(run_id)
        self._run_history_store.upsert(
            run_id=status.run_id,
            user_id=user_id,
            query=status.query,
            status=status.status,
            steps=list(status.steps),
        )

    def _persist_run_history_from_state(
        self,
        run_id: str,
        state: dict[str, Any],
        *,
        status: RunLifecycleStatus,
        steps: list[str] | tuple[str, ...] = (),
    ) -> None:
        user_id = str(state.get("user_id", "")).strip() or get_settings().rate_limit_default_user_id
        self._run_history_store.upsert(
            run_id=run_id,
            user_id=user_id,
            query=str(state.get("query", "")),
            status=status,
            steps=steps,
        )

    def _resolve_idempotent_run_id(
        self, idempotency_key: str | None, candidate_run_id: str
    ) -> tuple[str, bool]:
        """Claim idempotency_key for candidate_run_id, or resolve to the run a
        prior request already claimed it for.

        Returns (run_id, should_execute). should_execute is False when a
        prior request already owns this key -- the caller must return that
        existing run's status instead of starting a new execution for it.
        A no-op (always "start a new run") when no key was supplied or no
        idempotency_store is configured.
        """
        if not idempotency_key or self._idempotency_store is None:
            return candidate_run_id, True
        return self._idempotency_store.get_or_create(idempotency_key, candidate_run_id)

    def _existing_run_status(self, run_id: str, *, query: str) -> RunStatus:
        """Status for a run a duplicate request resolved to via idempotency.

        get_run() can raise RunNotFoundError in the brief window between the
        original request claiming the key and that same request's own
        create_initial_state()/_pending_runs write becoming visible -- report
        the same synthetic "running" status start_run() itself would return
        in that window rather than surfacing a spurious 404 for a run that
        genuinely does exist.
        """
        try:
            return self.get_run(run_id)
        except RunNotFoundError:
            return self._pending_status(run_id, {"query": query})

    def create_run(
        self,
        *,
        query: str,
        user_profile: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
        submitted_plan_text: str | None = None,
        idempotency_key: str | None = None,
    ) -> RunStatus:
        candidate_run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        resolved_run_id, should_execute = self._resolve_idempotent_run_id(
            idempotency_key, candidate_run_id
        )
        if not should_execute:
            return self._existing_run_status(resolved_run_id, query=query)
        self._rate_limiter.reserve_request(user_id)
        reset_llm_metrics()
        state = create_initial_state(
            run_id=resolved_run_id,
            thread_id=resolved_run_id,
            query=query,
            user_profile=user_profile,
            constraints=constraints,
            user_id=user_id,
            submitted_plan_text=submitted_plan_text,
        )
        config = build_graph_invoke_config(state)
        self._stream_with_timeout(state, config)
        # The business outcome (the stream above either finished or raised)
        # is decided by this point -- flush/metrics are best-effort and must
        # never turn a successful invoke into a reported failure.
        with best_effort("flush_langfuse", run_id=resolved_run_id):
            flush_langfuse()
        snapshot = self._graph.get_state(config)
        with best_effort("write_token_cost_log", run_id=resolved_run_id):
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next)
        run_status = self._to_status(
            resolved_run_id,
            snapshot.values,
            snapshot.next,
            interrupts=_collect_interrupts(snapshot),
        )
        with best_effort("persist_run_history", run_id=resolved_run_id):
            self._persist_run_history(resolved_run_id)
        return run_status

    def start_run(
        self,
        *,
        query: str,
        user_profile: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
        submitted_plan_text: str | None = None,
        idempotency_key: str | None = None,
    ) -> RunStatus:
        """Start a run in a background thread and return immediately."""
        candidate_run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        resolved_run_id, should_execute = self._resolve_idempotent_run_id(
            idempotency_key, candidate_run_id
        )
        if not should_execute:
            return self._existing_run_status(resolved_run_id, query=query)
        self._rate_limiter.reserve_request(user_id)
        reset_llm_metrics()
        state = create_initial_state(
            run_id=resolved_run_id,
            thread_id=resolved_run_id,
            query=query,
            user_profile=user_profile,
            constraints=constraints,
            user_id=user_id,
            submitted_plan_text=submitted_plan_text,
        )
        config = build_graph_invoke_config(state)
        with self._lock:
            self._run_failures.pop(resolved_run_id, None)
            self._pending_runs[resolved_run_id] = state
        # Opened here, synchronously, rather than as the first line inside
        # _execute_create_run: that runs on the background thread, which could
        # otherwise race an SSE client connecting to GET /runs/{run_id}/events
        # before the thread has actually opened the queue.
        self._open_event_stream(resolved_run_id)
        thread = threading.Thread(
            target=self._execute_create_run,
            args=(state, config, resolved_run_id),
            daemon=True,
            name=f"run-{resolved_run_id}",
        )
        thread.start()
        with best_effort("persist_run_history", run_id=resolved_run_id):
            self._persist_run_history_from_state(resolved_run_id, state, status="running")
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
            status = self._to_status(
                run_id, snapshot.values, snapshot.next, interrupts=_collect_interrupts(snapshot)
            )
            if pending is not None and status.status != "running":
                # A background thread (start_run/start_resume_run/start_profile_form_resume/
                # start_continue_run) is actively invoking the graph for this run_id, but the
                # checkpointer can still reflect the pre-resume snapshot for a brief window
                # right after the thread starts (it hasn't written its first update yet) --
                # e.g. the profile form's own missing-fields interrupt, still attached to the
                # old checkpoint. Report "running" so pollers keep waiting for the thread's
                # real outcome instead of settling on that stale pre-resume state.
                return replace(status, status="running")
            return status
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
        form_data: dict[str, Any] | None = None,
        submitted_plan_text: str | None = None,
    ) -> RunStatus:
        self._acquire_resume_guard(run_id)
        release_guard = True
        try:
            config = self._build_config(run_id)
            snapshot = self._graph.get_state(config)
            if not snapshot.values:
                raise RunNotFoundError(f"Run not found: {run_id}")

            if snapshot.next == ("user",):
                if form_data is None:
                    raise ValueError("form_data is required to resume the profile form")
                result = self.start_profile_form_resume(
                    run_id, form_data=form_data, submitted_plan_text=submitted_plan_text
                )
                release_guard = False
                return result

            if snapshot.next != ("hitl",) and not snapshot.values.get("waiting_for_user"):
                raise ValueError("Run is not waiting for HITL input")

            revision_count = int(snapshot.values.get("revision_count", 0))
            if decision_type is not None:
                decision = create_approval_decision(decision_type, message)
                update = decision_to_resume_update(decision, revision_count=revision_count)
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

            # Additive only: never overwrites submitted_plan_text with nothing when the
            # caller doesn't re-supply it on this resume -- the value already on state (or
            # in VFS) from an earlier turn survives untouched.
            if submitted_plan_text:
                update["submitted_plan_text"] = submitted_plan_text
                workspace_path = snapshot.values.get("workspace_path")
                if workspace_path:
                    VFS.for_run(Path(workspace_path)).write(
                        PLAN_SUBMITTED_TEXT, submitted_plan_text
                    )

            resolved_status = update.get("approval_status")
            if resolved_status == "revision_requested":
                # A resume starts execution at the paused "hitl" node directly
                # (interrupt_before=["hitl"]), never back through Supervisor,
                # so user_revision_to_replan_update's pending_request is what
                # routes this back to Fitness -- not a profile-gate reset.
                feedback = update.get("user_response") or message or ""
                update.update(
                    user_revision_to_replan_update(feedback, revision_count=revision_count)
                )
                workspace_path = snapshot.values.get("workspace_path")
                if workspace_path and update.get("revision_feedback"):
                    persist_revision_feedback(str(workspace_path), str(update["revision_feedback"]))
            result = self.start_resume_run(run_id, update=update)
            release_guard = False
            return result
        finally:
            if release_guard:
                self._release_resume_guard(run_id)

    def start_profile_form_resume(
        self,
        run_id: str,
        *,
        form_data: dict[str, Any],
        submitted_plan_text: str | None = None,
    ) -> RunStatus:
        """Resume a run paused at the profile form (dynamic `interrupt()`) with submitted data.

        Distinct from `start_resume_run` because the User subgraph pauses via `interrupt()`
        rather than the top-level `interrupt_before=["hitl"]` boundary, so resuming it means
        `Command(resume=form_data)`, not `Command(update=...)` alone -- though the two combine
        fine (they write to different channels; see `_execute_profile_form_resume`), which is
        how `submitted_plan_text` can be attached on this same call without disturbing
        `form_data`'s own merge into the profile.
        """
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")
        if snapshot.next != ("user",):
            raise ValueError("Run is not waiting for the profile form")
        self._claim_resume(run_id)

        with self._lock:
            self._run_failures.pop(run_id, None)
            self._pending_runs[run_id] = snapshot.values

        # Opened synchronously here (see start_run's identical comment) so a
        # racing SSE connection can never beat the background thread to it.
        self._open_event_stream(run_id)
        thread = threading.Thread(
            target=self._execute_profile_form_resume,
            args=(run_id, form_data, config, submitted_plan_text),
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
        submitted_plan_text: str | None = None,
    ) -> None:
        snapshot = self._graph.get_state(config)
        user_id = str(snapshot.values.get("user_id", ""))
        context_token = set_rate_limit_user_id(user_id or None)
        with best_effort("mark_run_tracked", run_id=run_id):
            self._mark_run_tracked(run_id, query=str(snapshot.values.get("query", "")))
        try:
            # Additive: only ever adds submitted_plan_text alongside the form-data resume,
            # never replaces state wholesale -- omitted, it leaves whatever's already on
            # state (or in VFS) from an earlier turn untouched.
            resume_command = (
                Command(update={"submitted_plan_text": submitted_plan_text}, resume=form_data)
                if submitted_plan_text
                else Command(resume=form_data)
            )
            if submitted_plan_text:
                workspace_path = snapshot.values.get("workspace_path")
                if workspace_path:
                    VFS.for_run(Path(workspace_path)).write(
                        PLAN_SUBMITTED_TEXT, submitted_plan_text
                    )
            self._stream_with_timeout(resume_command, config, run_id=run_id)
        except Exception as exc:
            logger.exception("Profile form resume for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        # The run's outcome is fully decided above -- everything below is
        # best-effort cleanup/observability/bookkeeping that must never be
        # allowed to change it.
        with best_effort("flush_langfuse", run_id=run_id):
            flush_langfuse()
        snapshot = self._graph.get_state(config)
        with self._lock:
            failed = run_id in self._run_failures
        with best_effort("write_token_cost_log", run_id=run_id):
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
        with best_effort("reset_rate_limit_user_id", run_id=run_id):
            reset_rate_limit_user_id(context_token)
        with self._lock:
            self._pending_runs.pop(run_id, None)
        with best_effort("sync_run_tracked", run_id=run_id):
            self._sync_run_tracked(run_id, snapshot, failed=failed)
        self._release_resume_guard(run_id)
        self._close_event_stream(run_id, final_status=self.get_run(run_id))

    def continue_run(self, run_id: str, *, message: str) -> RunStatus:
        """Replan from an existing conversation when the user changes plan preferences."""
        feedback = message.strip()
        if not feedback:
            raise ValueError("message is required")

        self._acquire_resume_guard(run_id)
        release_guard = True
        try:
            config = self._build_config(run_id)
            snapshot = self._graph.get_state(config)
            if not snapshot.values:
                raise RunNotFoundError(f"Run not found: {run_id}")

            lifecycle = _resolve_lifecycle_status(snapshot.values, snapshot.next)
            if lifecycle not in {"completed", "waiting_hitl"}:
                raise ValueError("Run cannot accept plan changes in its current state")

            # Built (and, if the shared replan budget is exhausted, raised) before
            # reserving rate-limit quota -- a rejected revision request shouldn't
            # consume a request from the user's daily cap.
            update = user_revision_to_replan_update(
                feedback, revision_count=int(snapshot.values.get("revision_count", 0))
            )
            self._rate_limiter.reserve_request(str(snapshot.values.get("user_id", "")) or None)
            # Unlike resume_run's in-flight revision (which resumes directly at the
            # paused "hitl" node), this re-enters at Supervisor (goto="supervisor" in
            # _execute_continue_run below) -- route_initial_from_supervisor's profile
            # gate then re-enters the User subgraph since profile_complete/profile_valid
            # is now False, so the revision text gets a chance to update the profile
            # before Fitness re-runs.
            update["profile_complete"] = False
            update["profile_valid"] = False
            update["current_node"] = "hitl"
            update["final_artifact_path"] = None
            workspace_path = snapshot.values.get("workspace_path")
            if workspace_path:
                persist_revision_feedback(str(workspace_path), feedback)

            if snapshot.next == ("hitl",) or snapshot.values.get("waiting_for_user"):
                result = self.start_resume_run(run_id, update=update)
            else:
                result = self.start_continue_run(run_id, update=update, config=config)
            release_guard = False
            return result
        finally:
            if release_guard:
                self._release_resume_guard(run_id)

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

        # Opened synchronously here (see start_run's identical comment) so a
        # racing SSE connection can never beat the background thread to it.
        self._open_event_stream(run_id)
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
        with best_effort("mark_run_tracked", run_id=run_id):
            self._mark_run_tracked(run_id, query=str(snapshot.values.get("query", "")))
        try:
            self._stream_with_timeout(
                Command(update=update, goto="supervisor"), config, run_id=run_id
            )
        except Exception as exc:
            logger.exception("Continue for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        # The run's outcome is fully decided above -- everything below is
        # best-effort cleanup/observability/bookkeeping that must never be
        # allowed to change it.
        with best_effort("flush_langfuse", run_id=run_id):
            flush_langfuse()
        snapshot = self._graph.get_state(config)
        with self._lock:
            failed = run_id in self._run_failures
        with best_effort("write_token_cost_log", run_id=run_id):
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
        with best_effort("reset_rate_limit_user_id", run_id=run_id):
            reset_rate_limit_user_id(context_token)
        with self._lock:
            self._pending_runs.pop(run_id, None)
        with best_effort("sync_run_tracked", run_id=run_id):
            self._sync_run_tracked(run_id, snapshot, failed=failed)
        self._release_resume_guard(run_id)
        self._close_event_stream(run_id, final_status=self.get_run(run_id))

    def start_resume_run(self, run_id: str, *, update: dict[str, Any]) -> RunStatus:
        """Resume a HITL-paused run in a background thread and return immediately."""
        config = self._build_config(run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.values:
            raise RunNotFoundError(f"Run not found: {run_id}")
        if snapshot.next != ("hitl",) and not snapshot.values.get("waiting_for_user"):
            raise ValueError("Run is not waiting for HITL input")
        self._claim_resume(run_id)

        with self._lock:
            self._run_failures.pop(run_id, None)
            self._pending_runs[run_id] = {**snapshot.values, **update}

        # Opened synchronously here (see start_run's identical comment) so a
        # racing SSE connection can never beat the background thread to it.
        self._open_event_stream(run_id)
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
        with best_effort("mark_run_tracked", run_id=run_id):
            self._mark_run_tracked(run_id, query=str(snapshot.values.get("query", "")))
        try:
            self._stream_with_timeout(Command(update=update), config, run_id=run_id)
        except Exception as exc:
            logger.exception("Resume for run %s failed", run_id)
            with self._lock:
                snapshot = self._graph.get_state(config)
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(snapshot.values.get("query", "")),
                }
        # The run's outcome is fully decided above -- everything below is
        # best-effort cleanup/observability/bookkeeping that must never be
        # allowed to change it.
        with best_effort("flush_langfuse", run_id=run_id):
            flush_langfuse()
        snapshot = self._graph.get_state(config)
        with self._lock:
            failed = run_id in self._run_failures
        with best_effort("write_token_cost_log", run_id=run_id):
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
        with best_effort("reset_rate_limit_user_id", run_id=run_id):
            reset_rate_limit_user_id(context_token)
        with self._lock:
            self._pending_runs.pop(run_id, None)
        with best_effort("sync_run_tracked", run_id=run_id):
            self._sync_run_tracked(run_id, snapshot, failed=failed)
        self._release_resume_guard(run_id)
        self._close_event_stream(run_id, final_status=self.get_run(run_id))

    def _execute_create_run(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        run_id: str,
    ) -> None:
        context_token = set_rate_limit_user_id(str(state.get("user_id", "")) or None)
        with best_effort("mark_run_tracked", run_id=run_id):
            self._mark_run_tracked(run_id, query=str(state.get("query", "")))
        try:
            self._stream_with_timeout(state, config, run_id=run_id)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            with self._lock:
                self._run_failures[run_id] = {
                    "error": str(exc),
                    "query": str(state.get("query", "")),
                }
        # The run's outcome is fully decided above -- everything below is
        # best-effort cleanup/observability/bookkeeping that must never be
        # allowed to change it.
        with best_effort("flush_langfuse", run_id=run_id):
            flush_langfuse()
        snapshot = self._graph.get_state(config)
        with self._lock:
            failed = run_id in self._run_failures
        with best_effort("write_token_cost_log", run_id=run_id):
            self._maybe_write_token_cost_log(snapshot.values, snapshot.next, failed=failed)
        with best_effort("reset_rate_limit_user_id", run_id=run_id):
            reset_rate_limit_user_id(context_token)
        with self._lock:
            self._pending_runs.pop(run_id, None)
        with best_effort("sync_run_tracked", run_id=run_id):
            self._sync_run_tracked(run_id, snapshot, failed=failed)
        self._close_event_stream(run_id, final_status=self.get_run(run_id))

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
            intent=None,
            response_mode=None,
            active_capability=None,
            final_response=None,
            final_artifact_path=None,
            final_plan=None,
            hitl_type=None,
            hitl_message=None,
            refusal_message=None,
            steps=(),
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
            intent=None,
            response_mode=None,
            active_capability=None,
            final_response=None,
            final_artifact_path=None,
            final_plan=None,
            hitl_type=None,
            hitl_message=failure.get("error"),
            refusal_message=None,
            steps=(),
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
        profile_form = (
            _extract_profile_form_payload(interrupts) if hitl_type == "profile_form" else None
        )
        ctx = state.get("execution_context") or {}
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
            intent=ctx.get("intent"),
            response_mode=ctx.get("response_mode"),
            active_capability=state.get("active_capability"),
            final_response=state.get("final_response"),
            final_artifact_path=state.get("final_artifact_path"),
            final_plan=final_plan,
            hitl_type=hitl_type,
            hitl_message=hitl_message,
            refusal_message=state.get("refusal_message"),
            steps=tuple(state.get("steps") or ()),
            next_nodes=next_nodes,
            error_message=None,
            profile_form=profile_form,
        )
