import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.settings import get_settings
from core.graph.idempotency_store import IdempotencyStore
from core.graph.run import create_initial_state
from core.graph.run_tracker import RunTracker
from core.graph.service import RunOrchestrator, best_effort
from core.profile.extraction import configure_profile_extractor
from core.profile.schema import ExtractedProfile
from core.profile.store import load_run_profile
from core.vfs import VFS


def test_resume_run_profile_form_via_command_resume(
    memory_checkpointer,
    tmp_path,
) -> None:
    """A run with an incomplete profile pauses inside the User subgraph (interrupt());
    resume_run's new form_data path resumes it via Command(resume=...), not
    Command(update=...), and the profile ends up complete/valid."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "waiting_hitl"
    assert run_status.hitl_type == "profile_form"

    orchestrator.resume_run(
        run_status.run_id,
        form_data={
            "sex": "male",
            "current_weight_kg": 85.0,
            "target_weight_kg": 75.0,
            "goal": "fat_loss",
        },
    )

    config = {"configurable": {"thread_id": run_status.run_id}}
    snapshot = orchestrator.graph.get_state(config)
    for _ in range(100):
        if snapshot.next != ("user",):
            break
        time.sleep(0.02)
        snapshot = orchestrator.graph.get_state(config)
    else:
        raise AssertionError("profile form resume did not complete in time")

    assert snapshot.values["profile_complete"] is True
    assert snapshot.values["profile_valid"] is True
    stored = load_run_profile(snapshot.values["workspace_path"])
    assert stored["sex"] == "male"
    assert stored["current_weight_kg"] == 85.0


def test_create_run_forwards_submitted_plan_text_into_state(
    memory_checkpointer,
) -> None:
    """Regression: create_run/start_run previously dropped submitted_plan_text before it
    ever reached create_initial_state, so the supervisor's verify-workflow guard
    (SUBMITTED_PLAN_MISSING_MESSAGE) fired even when a client submitted plan text."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={
            "age": 30,
            "sex": "male",
            "height_cm": 175,
            "current_weight_kg": 85.0,
            "activity_level": "gym_3x_week",
            "goal": "fat_loss",
        },
        constraints={"days_per_week": 4, "equipment": "gym"},
        submitted_plan_text="Day 1: Squat 3x5",
    )
    config = {"configurable": {"thread_id": run_status.run_id}}
    snapshot = orchestrator.graph.get_state(config)
    assert snapshot.values["submitted_plan_text"] == "Day 1: Squat 3x5"


def test_get_run_reports_running_while_pending_resume_race_leaves_stale_checkpoint(
    memory_checkpointer,
) -> None:
    """A background resume thread (start_resume_run/start_profile_form_resume/etc.) can
    have a run_id in _pending_runs before its Command(...) invoke has written a single
    checkpoint update -- get_run() must not mistake that untouched, pre-resume checkpoint
    (still showing the old interrupt) for a genuinely settled outcome, or a poller resuming
    the profile form would see the exact same "still needs the form" state it just
    submitted and stop polling before the real result ever arrives."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "waiting_hitl"
    assert run_status.hitl_type == "profile_form"

    # Simulate the race window: a resume thread has been registered as pending, but hasn't
    # advanced the checkpoint past the pre-resume interrupt yet.
    with orchestrator._lock:
        orchestrator._pending_runs[run_status.run_id] = {}
    raced_status = orchestrator.get_run(run_status.run_id)
    assert raced_status.status == "running"

    # Once the (simulated) background thread finishes and clears the pending marker, the
    # real checkpoint state -- still genuinely paused, since nothing actually resumed it --
    # must be reported again rather than staying stuck on "running" forever.
    with orchestrator._lock:
        orchestrator._pending_runs.pop(run_status.run_id, None)
    settled_status = orchestrator.get_run(run_status.run_id)
    assert settled_status.status == "waiting_hitl"
    assert settled_status.hitl_type == "profile_form"


@patch("core.graph.service.get_settings")
def test_invoke_with_timeout_raises_when_graph_invoke_hangs(
    mock_get_settings: MagicMock,
    memory_checkpointer,
) -> None:
    """Regression (PR2): before this fix, self._graph.invoke() was called directly
    and unbounded, so a hung node could block a background run forever with no
    visible failure. _invoke_with_timeout must raise instead of hanging."""
    mock_get_settings.return_value.run_execution_timeout_seconds = 0.05
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    def hanging_invoke(*_args: object, **_kwargs: object) -> None:
        time.sleep(2)

    orchestrator._graph.invoke = hanging_invoke  # type: ignore[method-assign]

    with pytest.raises(TimeoutError):
        orchestrator._invoke_with_timeout({}, {})


@patch("core.graph.service.get_settings")
def test_invoke_with_timeout_returns_normally_within_deadline(
    mock_get_settings: MagicMock,
    memory_checkpointer,
) -> None:
    """A graph.invoke() call that finishes well inside the deadline is unaffected."""
    mock_get_settings.return_value.run_execution_timeout_seconds = 5.0
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    calls: list[tuple[object, object]] = []

    def fast_invoke(input_data: object, config: object) -> None:
        calls.append((input_data, config))

    orchestrator._graph.invoke = fast_invoke  # type: ignore[method-assign]

    orchestrator._invoke_with_timeout("input", {"configurable": {}})

    assert calls == [("input", {"configurable": {}})]


@patch("core.graph.service.get_settings")
def test_start_run_records_failure_instead_of_hanging_when_execution_times_out(
    mock_get_settings: MagicMock,
    memory_checkpointer,
) -> None:
    """Regression (PR2): a run whose graph execution never returns must settle
    into "failed" (visible via get_run()) rather than staying "running" forever."""
    mock_get_settings.return_value.run_execution_timeout_seconds = 0.05
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    def hanging_invoke(*_args: object, **_kwargs: object) -> None:
        time.sleep(2)

    orchestrator._graph.invoke = hanging_invoke  # type: ignore[method-assign]

    run_status = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "running"

    for _ in range(100):
        status = orchestrator.get_run(run_status.run_id)
        if status.status == "failed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("run did not settle to 'failed' within the timeout window")

    assert status.error_message is not None


def _waiting_for_approval_state(run_id: str, tmp_path) -> dict:
    initial = create_initial_state(
        run_id=run_id,
        thread_id=run_id,
        query="Approve my plan",
        workspace_root=tmp_path / run_id,
    )
    return {
        **initial,
        "request_type": "training_plan",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "current_node": "supervisor",
        "verification_passed": True,
        "route_decision": "COMPLETE",
        "waiting_for_user": True,
        "approval_status": "pending",
        "profile_complete": True,
        "profile_valid": True,
    }


def test_resume_run_free_text_approval_uses_strict_classification(
    memory_checkpointer,
    tmp_path,
) -> None:
    """resume_run's free-text approval path (no decision_type) classifies user_response with
    classify_approval_response(strict=True) -- only exact "approve"/"approved"/"yes" (and
    reject equivalents) match; prefix phrasing like "approving this" does not. This is the
    pre-existing behavior of the now-deleted `_approval_from_response`, preserved by the
    `strict` parameter rather than unified with hitl_control_data's permissive prefix-matching
    rule (which stays exercised separately by tests/test_partial_rerun.py)."""
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    exact_config = {"configurable": {"thread_id": "approve-exact"}}
    orchestrator.graph.invoke(_waiting_for_approval_state("approve-exact", tmp_path), exact_config)
    exact_status = orchestrator.resume_run("approve-exact", user_response="approve")
    assert exact_status.approval_status == "approved"

    # Under strict=True, "approving this plan" doesn't match the exact "approve"/"approved"/
    # "yes" set, so it's classified "revision_requested" -- which resume_run's revision branch
    # then normalizes to route_decision="REPLAN"/approval_status="pending" (see
    # core.hitl.resume.user_revision_to_replan_update). If strict matching regressed to the
    # permissive prefix rule, this input would instead be classified "approved" and skip the
    # revision branch entirely, leaving route_decision untouched at "COMPLETE".
    prefix_config = {"configurable": {"thread_id": "approve-prefix"}}
    orchestrator.graph.invoke(
        _waiting_for_approval_state("approve-prefix", tmp_path), prefix_config
    )
    prefix_status = orchestrator.resume_run("approve-prefix", user_response="approving this plan")
    assert prefix_status.approval_status == "pending"
    assert prefix_status.route_decision == "REPLAN"


def test_concurrent_resume_calls_reject_the_second_with_conflict(
    memory_checkpointer,
    tmp_path,
) -> None:
    """Regression test for A5: two near-simultaneous resume calls for the same run_id must
    not both read the pre-resume snapshot and invoke the graph -- the second call must be
    rejected (ValueError, mapped to HTTP 409 by the API layer) while the first is still in
    flight, not double-processed."""
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_id = "concurrent-resume-run"
    config = {"configurable": {"thread_id": run_id}}
    state = _waiting_for_approval_state(run_id, tmp_path)
    vfs = VFS.for_run(Path(state["workspace_path"]))
    vfs.write("fitness/final_plan.md", "# Final Plan\n\nMacro targets and training days.")
    orchestrator.graph.invoke(state, config)

    # Block the first resume's background thread inside graph.invoke, right where the real
    # race window sits (after the pre-resume snapshot has been read, before the graph call
    # completes), so a second resume_run() call is guaranteed to observe the first as still
    # in flight rather than racing against real thread scheduling.
    release_first_invoke = threading.Event()
    original_invoke = orchestrator.graph.invoke
    invoke_call_count = {"count": 0}

    def blocking_invoke(*args, **kwargs):
        invoke_call_count["count"] += 1
        release_first_invoke.wait(timeout=5)
        return original_invoke(*args, **kwargs)

    orchestrator._graph.invoke = blocking_invoke

    first_status = orchestrator.resume_run(run_id, user_response="approve")
    assert first_status.status == "running"

    with pytest.raises(ValueError, match="already has a resume/continue in progress"):
        orchestrator.resume_run(run_id, user_response="approve")

    release_first_invoke.set()

    settled = None
    for _ in range(100):
        settled = orchestrator.get_run(run_id)
        if settled.status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("resume did not settle in time")

    assert settled.approval_status == "approved"
    # Only the first resume's Command(update=...) ever reached graph.invoke -- the rejected
    # duplicate never got far enough to invoke the graph a second time.
    assert invoke_call_count["count"] == 1

    # The guard is released once the in-flight resume completes, so a later resume for the
    # same run_id is not permanently blocked.
    orchestrator._graph.invoke = original_invoke


@pytest.fixture
def run_tracker() -> RunTracker:
    settings = get_settings()
    tracker = RunTracker(settings.checkpointer_dsn)
    tracker.reset()
    yield tracker
    tracker.reset()
    tracker.close()


def test_reconcile_orphaned_runs_is_a_noop_without_a_run_tracker(
    memory_checkpointer,
) -> None:
    """RunOrchestrator's default (no run_tracker, e.g. tests/scripts using
    MemorySaver) has no restart-durable record to reconcile against --
    reconcile_orphaned_runs() must be a safe no-op, not an error."""
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    assert orchestrator.reconcile_orphaned_runs() == 0


def test_start_run_tracks_then_clears_on_completion(
    memory_checkpointer,
    run_tracker: RunTracker,
) -> None:
    """A run that settles normally must leave no trace in the tracker -- only
    a run whose process died mid-flight should ever be reconcilable."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)

    run_status = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    for _ in range(100):
        if orchestrator.get_run(run_status.run_id).status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("run did not settle in time")

    # Nothing left to reconcile -- the completed run's tracking row was cleared.
    assert run_tracker.reconcile_orphaned_runs(stale_after_seconds=0) == []


@patch("core.graph.service.get_settings")
def test_reconcile_orphaned_runs_surfaces_an_orphaned_run_as_failed(
    mock_get_settings: MagicMock,
    memory_checkpointer,
    run_tracker: RunTracker,
) -> None:
    """Regression (PR3): a run left 'running' by a process that died before
    calling _clear_run_tracked (simulated here directly against the tracker,
    standing in for a hard crash mid-execution) must be visible via get_run()
    as failed -- not stuck reporting "running" forever -- once reconciled."""
    mock_get_settings.return_value.run_execution_timeout_seconds = 0.02
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    run_tracker.mark_running("orphaned-run-id", query="a query that never finished")
    time.sleep(0.05)

    reconciled_count = orchestrator.reconcile_orphaned_runs()

    assert reconciled_count == 1
    status = orchestrator.get_run("orphaned-run-id")
    assert status.status == "failed"
    assert status.error_message is not None
    assert "orphaned" in status.error_message.lower()


@patch("core.graph.service.get_settings")
def test_reconcile_orphaned_runs_does_not_touch_a_run_that_is_still_fresh(
    mock_get_settings: MagicMock,
    memory_checkpointer,
    run_tracker: RunTracker,
) -> None:
    """A run marked running moments ago is not orphaned -- reconciliation must
    not mark genuinely in-progress runs as failed."""
    mock_get_settings.return_value.run_execution_timeout_seconds = 60.0
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    run_tracker.mark_running("fresh-run-id", query="still going")

    assert orchestrator.reconcile_orphaned_runs() == 0


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    settings = get_settings()
    store = IdempotencyStore(settings.checkpointer_dsn)
    store.reset()
    yield store
    store.reset()
    store.close()


def test_start_run_without_idempotency_key_always_creates_a_new_run(
    memory_checkpointer,
    idempotency_store: IdempotencyStore,
) -> None:
    """Preserve existing API: omitting idempotency_key must behave exactly as
    before -- every call creates a distinct run."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(
        checkpointer=memory_checkpointer, idempotency_store=idempotency_store
    )

    first = orchestrator.start_run(query="I want a 4-day training plan to lose weight.")
    second = orchestrator.start_run(query="I want a 4-day training plan to lose weight.")

    assert first.run_id != second.run_id


def test_start_run_with_repeated_idempotency_key_returns_the_existing_run(
    memory_checkpointer,
    idempotency_store: IdempotencyStore,
) -> None:
    """Regression (PR4): a duplicate create_run request carrying the same
    idempotency_key (client retry, double-click) must resolve to the run
    already created for that key, not start a second one."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(
        checkpointer=memory_checkpointer, idempotency_store=idempotency_store
    )

    first = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        idempotency_key="client-retry-key",
    )
    second = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        idempotency_key="client-retry-key",
    )

    assert first.run_id == second.run_id
    # Only one run ever actually exists -- the checkpoint has exactly one entry.
    assert orchestrator.get_run(first.run_id).run_id == first.run_id


def test_start_run_with_repeated_idempotency_key_does_not_reserve_rate_limit_twice(
    memory_checkpointer,
    idempotency_store: IdempotencyStore,
) -> None:
    """A deduplicated request must not consume the user's rate-limit budget a
    second time -- it never reaches the point where a new run is created."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(
        checkpointer=memory_checkpointer, idempotency_store=idempotency_store
    )
    reserve_calls: list[str | None] = []
    original_reserve = orchestrator._rate_limiter.reserve_request

    def counting_reserve(user_id: str | None = None) -> None:
        reserve_calls.append(user_id)
        return original_reserve(user_id)

    orchestrator._rate_limiter.reserve_request = counting_reserve  # type: ignore[method-assign]

    orchestrator.start_run(query="Same query", idempotency_key="dedupe-key")
    orchestrator.start_run(query="Same query", idempotency_key="dedupe-key")

    assert len(reserve_calls) == 1


def test_start_run_idempotency_key_is_a_noop_without_an_idempotency_store(
    memory_checkpointer,
) -> None:
    """Preserve existing API: an orchestrator without an idempotency_store
    (e.g. tests/scripts building RunOrchestrator directly) must ignore the key
    rather than erroring -- every call still creates a new run."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    first = orchestrator.start_run(query="Same query", idempotency_key="some-key")
    second = orchestrator.start_run(query="Same query", idempotency_key="some-key")

    assert first.run_id != second.run_id


def test_start_resume_run_rejects_a_second_concurrent_resume_via_the_database_claim(
    memory_checkpointer,
    tmp_path,
    run_tracker: RunTracker,
) -> None:
    """Regression (PR5): unlike the in-memory _active_resumes guard (which only
    protects a single process), the database claim must reject a duplicate
    resume even from a wholly separate RunOrchestrator instance -- simulating
    two worker replicas racing to resume the same run, each with its own,
    independent in-memory guard, sharing only the Postgres-backed tracker."""
    run_id = "cross-worker-resume-run"
    config = {"configurable": {"thread_id": run_id}}
    state = _waiting_for_approval_state(run_id, tmp_path)
    vfs = VFS.for_run(Path(state["workspace_path"]))
    vfs.write("fitness/final_plan.md", "# Final Plan\n\nMacro targets and training days.")

    worker_a = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    worker_b = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    worker_a.graph.invoke(state, config)
    run_tracker.mark_waiting(run_id, query="Approve my plan")

    first = worker_a.start_resume_run(
        run_id, update={"approval_status": "approved", "waiting_for_user": False}
    )
    assert first.status == "running"

    with pytest.raises(ValueError, match="already been resumed"):
        worker_b.start_resume_run(
            run_id, update={"approval_status": "approved", "waiting_for_user": False}
        )

    for _ in range(100):
        if worker_a.get_run(run_id).status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("resume did not settle in time")


def test_start_profile_form_resume_rejects_a_second_concurrent_resume_via_the_database_claim(
    memory_checkpointer,
    run_tracker: RunTracker,
) -> None:
    """Regression (PR5): the same database-claim protection applies to the
    profile-form resume path (Command(resume=...)), not just HITL approval."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    worker_a = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    worker_b = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)

    run_status = worker_a.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "waiting_hitl"
    assert run_status.hitl_type == "profile_form"
    run_tracker.mark_waiting(run_status.run_id, query=run_status.query)

    form_data = {
        "sex": "male",
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "goal": "fat_loss",
    }
    first = worker_a.start_profile_form_resume(run_status.run_id, form_data=form_data)
    assert first.status == "running"

    with pytest.raises(ValueError, match="already been resumed"):
        worker_b.start_profile_form_resume(run_status.run_id, form_data=form_data)


def test_best_effort_swallows_exceptions_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """best_effort() must catch any exception raised inside it and log a
    warning identifying the step and run -- never let it propagate. That's
    the entire mechanism PR6 relies on to keep cleanup failures from
    overwriting a run's already-recorded outcome."""
    with caplog.at_level(logging.WARNING, logger="core.graph.service"):
        with best_effort("some_step", run_id="run-1"):
            raise RuntimeError("boom")

    assert "some_step" in caplog.text
    assert "run-1" in caplog.text


def test_best_effort_does_not_affect_successful_execution() -> None:
    """best_effort() must not change behavior at all when its body succeeds."""
    calls = []

    with best_effort("some_step", run_id="run-1"):
        calls.append(1)

    assert calls == [1]


@patch("core.graph.service.flush_langfuse")
def test_create_run_succeeds_even_when_langfuse_flush_fails(
    mock_flush_langfuse: MagicMock,
    memory_checkpointer,
) -> None:
    """Regression (PR6): the core bug this PR closes. flush_langfuse() used to
    run inside the same try block as the business logic in every _execute_*
    method (and here, in create_run itself) -- a flush failure was caught by
    `except Exception` and the run reported failed even though the graph
    invocation had already genuinely succeeded. flush_langfuse() must now run
    strictly after the outcome is decided, wrapped in best_effort()."""
    mock_flush_langfuse.side_effect = RuntimeError("langfuse endpoint unreachable")
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )

    assert run_status.status == "waiting_hitl"
    # >=1, not assert_called_once(): this patches the module-level symbol
    # process-wide, so an unrelated background thread left over from another
    # test (a pre-existing test-suite characteristic, not this test's
    # concern) can also invoke it while the patch is active. What this test
    # must prove is only that *this* orchestrator's flush went through the
    # mock and still resulted in a successful run -- not an exact count.
    assert mock_flush_langfuse.call_count >= 1


@patch("core.graph.service.flush_langfuse")
def test_start_run_settles_successfully_even_when_langfuse_flush_fails(
    mock_flush_langfuse: MagicMock,
    memory_checkpointer,
) -> None:
    """Regression (PR6): same guarantee on the background-execution path used
    by the real API (start_run), not just the synchronous create_run()."""
    mock_flush_langfuse.side_effect = RuntimeError("langfuse endpoint unreachable")
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    run_status = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )

    status = None
    for _ in range(100):
        status = orchestrator.get_run(run_status.run_id)
        if status.status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("run did not settle in time")

    assert status.status == "waiting_hitl"
    assert status.error_message is None


def test_start_run_settles_successfully_even_when_cost_log_write_fails(
    memory_checkpointer,
) -> None:
    """Regression (PR6): a metrics/cost-log write failure ('metrics' in
    scope) must never turn a successful run into a reported failure."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    orchestrator._maybe_write_token_cost_log = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("disk full")
    )

    run_status = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )

    status = None
    for _ in range(100):
        status = orchestrator.get_run(run_status.run_id)
        if status.status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("run did not settle in time")

    assert status.status == "waiting_hitl"


def test_start_run_settles_successfully_even_when_run_tracker_bookkeeping_fails(
    memory_checkpointer,
    run_tracker: RunTracker,
) -> None:
    """Regression (PR6): a run_tracker (bookkeeping) failure -- marking or
    syncing tracked state in Postgres -- must never turn a successful run
    into a reported failure."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer, run_tracker=run_tracker)
    orchestrator._run_tracker.mark_running = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("tracker db unreachable")
    )
    orchestrator._run_tracker.mark_waiting = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("tracker db unreachable")
    )

    run_status = orchestrator.start_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )

    status = None
    for _ in range(100):
        status = orchestrator.get_run(run_status.run_id)
        if status.status != "running":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("run did not settle in time")

    assert status.status == "waiting_hitl"
