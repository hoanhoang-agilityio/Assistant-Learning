from core.graph.run_history_store import InMemoryRunHistoryStore


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
