from datetime import UTC, datetime, timedelta

from core.adapters.db.run_history_store import InMemoryRunHistoryStore


def test_upsert_and_list_by_user_returns_newest_first() -> None:
    store = InMemoryRunHistoryStore()
    store.upsert(
        run_id="run_a",
        user_id="alice",
        query="First plan",
        status="completed",
        steps=["supervisor:classify"],
    )
    store.upsert(
        run_id="run_b",
        user_id="alice",
        query="Second plan",
        status="waiting_hitl",
        steps=["supervisor:classify", "fitness:planner"],
    )
    store.upsert(
        run_id="run_other",
        user_id="bob",
        query="Bob plan",
        status="completed",
        steps=[],
    )

    alice_runs = store.list_by_user("alice", limit=10)
    assert [run.run_id for run in alice_runs] == ["run_b", "run_a"]
    assert alice_runs[0].steps == ("supervisor:classify", "fitness:planner")
    assert store.list_by_user("bob", limit=10)[0].query == "Bob plan"


def test_upsert_updates_existing_run() -> None:
    store = InMemoryRunHistoryStore()
    store.upsert(
        run_id="run_a",
        user_id="alice",
        query="Draft",
        status="running",
        steps=[],
    )
    store.upsert(
        run_id="run_a",
        user_id="alice",
        query="Draft",
        status="completed",
        steps=["supervisor:classify", "persist"],
    )

    runs = store.list_by_user("alice", limit=10)
    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].steps == ("supervisor:classify", "persist")


def test_list_recent_completed_filters_status_and_since_and_orders_oldest_first() -> None:
    store = InMemoryRunHistoryStore()
    store.upsert(run_id="run_completed", user_id="alice", query="Q1", status="completed", steps=[])
    store.upsert(run_id="run_running", user_id="alice", query="Q2", status="running", steps=[])
    store.upsert(run_id="run_failed", user_id="bob", query="Q3", status="failed", steps=[])
    store.upsert(run_id="run_completed_2", user_id="bob", query="Q4", status="completed", steps=[])

    since = datetime.now(tz=UTC) - timedelta(minutes=1)
    recent = store.list_recent_completed(since=since, limit=10)
    assert [run.run_id for run in recent] == ["run_completed", "run_completed_2"]

    future = datetime.now(tz=UTC) + timedelta(minutes=1)
    assert store.list_recent_completed(since=future, limit=10) == []

    assert len(store.list_recent_completed(since=since, limit=1)) == 1
