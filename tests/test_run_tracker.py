"""Tests for RunTracker (PR3: orphan reconciliation; PR5: duplicate-resume
prevention via mark_waiting/claim_resume).

Runs against the real local Postgres instance already used by
core.graph.checkpointer/core.rate_limit.postgres_store in this dev
environment (docker-compose's postgres service) -- mirrors
core/rate_limit/postgres_store.py's own untested-at-the-unit-level
precedent by instead exercising the real table, which is worth the
small dependency here since orphan reconciliation's correctness hinges
entirely on the UPDATE's WHERE clause and interval arithmetic.
"""

from __future__ import annotations

import threading
import time

import pytest

from core.config.settings import get_settings
from core.graph.run_tracker import RunTracker


@pytest.fixture
def run_tracker() -> RunTracker:
    settings = get_settings()
    tracker = RunTracker(settings.checkpointer_dsn)
    tracker.reset()
    yield tracker
    tracker.reset()
    tracker.close()


def test_mark_running_then_clear_leaves_no_row(run_tracker: RunTracker) -> None:
    """A run that settles normally must not be reconcilable -- clear() removes
    its row entirely rather than leaving it in some 'done' status."""
    run_tracker.mark_running("run-1", query="test query")
    run_tracker.clear("run-1")

    orphaned = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0)

    assert orphaned == []


def test_reconcile_orphaned_runs_marks_stale_running_rows_failed(
    run_tracker: RunTracker,
) -> None:
    """Regression (PR3): a run whose tracking row is still 'running' past the
    staleness window must be reconciled -- this is the core orphan-recovery
    behavior; without it a crashed process's runs are stuck 'running' forever."""
    run_tracker.mark_running("run-orphaned", query="orphaned query")
    time.sleep(0.05)

    orphaned = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)

    assert orphaned == [("run-orphaned", "orphaned query")]


def test_reconcile_orphaned_runs_leaves_fresh_running_rows_alone(
    run_tracker: RunTracker,
) -> None:
    """A run that started moments ago is not orphaned -- it's just running."""
    run_tracker.mark_running("run-fresh", query="fresh query")

    orphaned = run_tracker.reconcile_orphaned_runs(stale_after_seconds=60)

    assert orphaned == []


def test_reconcile_orphaned_runs_does_not_retry_already_reconciled_rows(
    run_tracker: RunTracker,
) -> None:
    """Regression (PR3, explicit 'no automatic retry' requirement): once a row
    is marked failed/orphaned, a second reconciliation pass must not touch it
    again -- the WHERE status = 'running' clause excludes it permanently."""
    run_tracker.mark_running("run-orphaned", query="orphaned query")
    time.sleep(0.05)

    first_pass = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)
    second_pass = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)

    assert first_pass == [("run-orphaned", "orphaned query")]
    assert second_pass == []


def test_reconcile_orphaned_runs_is_safe_to_call_concurrently(
    run_tracker: RunTracker,
) -> None:
    """Regression (PR3, 'single SQL UPDATE strategy', no leader election): two
    reconciliation calls racing on the same stale row (e.g. a periodic sweep
    firing at the same moment as a startup sweep in another replica) must
    only have one of them actually claim the row -- never both."""
    run_tracker.mark_running("run-orphaned", query="orphaned query")
    time.sleep(0.05)

    first = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)
    second = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)

    combined = first + second
    assert combined == [("run-orphaned", "orphaned query")]


def test_mark_running_refreshes_an_existing_row(run_tracker: RunTracker) -> None:
    """A resumed run (start_resume_run after start_run already tracked it)
    refreshes updated_at rather than erroring on a duplicate key."""
    run_tracker.mark_running("run-1", query="first query")
    run_tracker.mark_running("run-1", query="second query")

    orphaned = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)
    assert orphaned == []  # freshly (re-)marked, not stale

    time.sleep(0.05)
    orphaned = run_tracker.reconcile_orphaned_runs(stale_after_seconds=0.02)
    assert orphaned == [("run-1", "second query")]


def test_mark_waiting_then_claim_resume_succeeds_once(run_tracker: RunTracker) -> None:
    """A run that settled waiting for user input can be claimed for resume
    exactly once -- the transition to 'running' is what the claim performs."""
    run_tracker.mark_waiting("run-1", query="approve my plan?")

    assert run_tracker.claim_resume("run-1") is True


def test_claim_resume_rejects_a_second_attempt(run_tracker: RunTracker) -> None:
    """Regression (PR5): once a run has been resumed, a second resume attempt
    for the same run_id must be rejected -- the row is no longer 'waiting_hitl'
    after the first claim transitions it to 'running'."""
    run_tracker.mark_waiting("run-1", query="approve my plan?")

    first_claim = run_tracker.claim_resume("run-1")
    second_claim = run_tracker.claim_resume("run-1")

    assert first_claim is True
    assert second_claim is False


def test_claim_resume_rejects_a_run_that_is_not_waiting(run_tracker: RunTracker) -> None:
    """A run that's actively 'running' (not paused for user input) must not be
    claimable as a resume -- there's nothing to resume."""
    run_tracker.mark_running("run-1", query="still executing")

    assert run_tracker.claim_resume("run-1") is False


def test_claim_resume_rejects_an_unknown_run(run_tracker: RunTracker) -> None:
    """No tracked row at all (never marked waiting) must not be claimable."""
    assert run_tracker.claim_resume("no-such-run") is False


def test_claim_resume_is_safe_under_concurrent_duplicate_requests(
    run_tracker: RunTracker,
) -> None:
    """Regression (PR5, 'single atomic UPDATE', no optimistic locking / version
    column): ten callers racing to resume the same waiting run -- exactly what
    two worker replicas handling a client's double-click looks like -- must
    result in exactly one winner."""
    run_tracker.mark_waiting("race-run", query="approve my plan?")
    results: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        result = run_tracker.claim_resume("race-run")
        with lock:
            results.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == 9
