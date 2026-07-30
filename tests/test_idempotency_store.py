"""Tests for IdempotencyStore (PR4: idempotency support for create_run).

Runs against the real local Postgres instance already used by
core.orchestration.graph.checkpointer/core.rate_limit.postgres_store/core.orchestration.graph.run_tracker
in this dev environment (docker-compose's postgres service).
"""

from __future__ import annotations

import threading

import pytest

from core.config.settings import get_settings
from core.orchestration.graph.idempotency_store import IdempotencyStore


@pytest.fixture
def idempotency_store() -> IdempotencyStore:
    settings = get_settings()
    store = IdempotencyStore(settings.checkpointer_dsn)
    store.reset()
    yield store
    store.reset()
    store.close()


def test_get_or_create_claims_a_new_key(idempotency_store: IdempotencyStore) -> None:
    run_id, created = idempotency_store.get_or_create("key-1", "run-1")

    assert run_id == "run-1"
    assert created is True


def test_get_or_create_returns_existing_run_for_a_repeated_key(
    idempotency_store: IdempotencyStore,
) -> None:
    """Regression (PR4): a duplicate request (same key, a freshly generated
    candidate run_id) must resolve to the ORIGINAL run, not create a second one."""
    first_run_id, first_created = idempotency_store.get_or_create("key-1", "run-1")
    second_run_id, second_created = idempotency_store.get_or_create("key-1", "run-2")

    assert first_created is True
    assert second_created is False
    assert first_run_id == "run-1"
    assert second_run_id == "run-1"  # the second candidate ("run-2") is discarded


def test_different_keys_each_claim_their_own_run(idempotency_store: IdempotencyStore) -> None:
    run_id_a, created_a = idempotency_store.get_or_create("key-a", "run-a")
    run_id_b, created_b = idempotency_store.get_or_create("key-b", "run-b")

    assert (run_id_a, created_a) == ("run-a", True)
    assert (run_id_b, created_b) == ("run-b", True)


def test_get_or_create_is_safe_under_concurrent_duplicate_requests(
    idempotency_store: IdempotencyStore,
) -> None:
    """Regression (PR4, 'unique constraint'): two requests racing on the same
    key -- exactly what a real double-click/client-retry looks like -- must
    result in exactly one winner, never two runs claiming the same key."""
    results: list[tuple[str, bool]] = []
    lock = threading.Lock()

    def attempt(candidate_run_id: str) -> None:
        result = idempotency_store.get_or_create("race-key", candidate_run_id)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=attempt, args=(f"run-{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [run_id for run_id, created in results if created]
    resolved_run_ids = {run_id for run_id, _ in results}
    assert len(winners) == 1
    assert resolved_run_ids == {winners[0]}
