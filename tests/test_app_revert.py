"""Tests for the revert branch.

The one property that matters most here is that **revert is an append, not a
rewind**. Restoring v1 must produce a v3 whose
content is v1's, with v2 still on record — otherwise the user cannot undo their
undo, and they will want to.

The rest follows from that: a restored plan is a *draft* until confirmed, it is
re-verified against the profile the user has now rather than the one they had
then, and an ambiguous request lists the options instead of guessing.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.planning.state import ExerciseChoices
from app.core.langgraph.graph import LangGraphAgent, _add_nodes
from app.core.langgraph.versioning import (
    VersionChoice,
    describe_verification_reason,
    render_versions,
    resolve_version_id,
)
from app.schemas.graph import IntentDecision, ProfileExtraction, RootState

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_seed.json"

pytestmark = pytest.mark.skipif(
    not _CATALOG_FILE.exists(),
    reason="data/exercise_seed.json is missing — the catalog fixture needs it",
)

PROFILE = {
    "weight_kg": 75.0,
    "height_cm": 175.0,
    "age": 28,
    "sex": "male",
    "activity_level": "light",
    "days_per_week": 4,
    "level": 3,
    "goal": "fat_loss",
    "equipment": ["barbell", "cable", "dumbbell", "machine", "bodyweight"],
    "injuries": [],
    "preferences": "",
}

_DEFAULTS = {
    name: (f.default_factory() if f.default_factory else f.default)
    for name, f in RootState.model_fields.items()
}

_REF = [
    {"version_id": "v3-id", "label": "v3", "created_at": "2026-08-03T00:00:00"},
    {"version_id": "v2-id", "label": "v2", "created_at": "2026-08-02T00:00:00"},
    {"version_id": "v1-id", "label": "v1", "created_at": "2026-08-01T00:00:00"},
]


@dataclass
class _StoredVersion:
    """Stand-in for a PlanVersion row."""

    id: str
    label: str
    plan: dict[str, Any]
    macros: dict[str, Any]
    profile_hash: str
    rubric_version: str = "2026.2"
    created_at: str = "2026-08-01T00:00:00"
    parent_id: str | None = None
    restored_from: str | None = None
    extras: dict = field(default_factory=dict)


def _plan(days: int, name: str) -> dict:
    """A minimal but structurally valid plan."""
    return {
        "template_id": "upper_lower_4day",
        "days": [
            {
                "name": f"{name} day {index + 1}",
                "exercises": [
                    {
                        "slot_id": f"s{index}",
                        "exercise_id": "barbell_bench_press",
                        "name": "Barbell Bench Press",
                        "sets": 4,
                        "reps": [6, 8],
                        "rir": [1, 2],
                    }
                ],
            }
            for index in range(days)
        ],
    }


class _FakeLLM:
    """Module-scoped stand-in for the shared llm_service singleton."""

    def bind_tools(self, _tools):
        """No-op: the agent binds tools at construction."""
        return self

    async def call(self, _messages, *_args, **kwargs):
        response_format = kwargs.get("response_format")
        if response_format is ProfileExtraction:
            return ProfileExtraction()
        if response_format is ExerciseChoices:
            return ExerciseChoices(choices=[])
        if response_format is not None:
            return response_format()
        return AIMessage(content="Restored.")


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture
def pipeline(monkeypatch, catalog):
    """Compile the root graph with version storage stubbed in memory."""
    calls: dict[str, list] = {"versions": []}
    stored = {
        "v1-id": _StoredVersion("v1-id", "v1", _plan(4, "v1"), {"kcal": 2100}, "hash-old"),
        "v2-id": _StoredVersion("v2-id", "v2", _plan(5, "v2"), {"kcal": 2300}, "hash-old"),
        "v3-id": _StoredVersion("v3-id", "v3", _plan(3, "v3"), {"kcal": 2000}, "hash-old"),
    }

    monkeypatch.setattr("app.core.langgraph.graph.load_catalog", lambda *a, **k: catalog)

    async def fake_version_index(_user_id):
        return list(_REF)

    async def fake_get_version(version_id):
        return stored.get(version_id)

    async def fake_insert_version(**kwargs):
        calls["versions"].append(kwargs)
        return {"version_id": "v4-id", "label": "v4", "created_at": "2026-08-04T00:00:00"}

    async def fake_get_profile(_user_id):
        return dict(PROFILE)

    async def fake_upsert(_user_id, _profile):
        return None

    monkeypatch.setattr("app.core.langgraph.graph.version_index", fake_version_index)
    monkeypatch.setattr("app.core.langgraph.graph.get_version", fake_get_version)
    monkeypatch.setattr("app.core.langgraph.graph.insert_version", fake_insert_version)
    monkeypatch.setattr(
        "app.core.langgraph.profile.nodes.profile_service.get_profile", fake_get_profile
    )

    # `load_context` reads two stores besides the profile. Stubbed so a test
    # asserts what it set up, not what happens to be seeded in the developer's
    # Postgres — the graph state a test passes in is the only plan it has.
    async def fake_latest_version(_user_id):
        return None

    async def fake_recent_episodes(_user_id, _session_id):
        return ""

    monkeypatch.setattr("app.core.langgraph.profile.nodes.latest_version", fake_latest_version)
    monkeypatch.setattr("app.core.langgraph.profile.nodes.recent_episodes", fake_recent_episodes)
    monkeypatch.setattr(
        "app.core.langgraph.profile.nodes.profile_service.upsert_profile", fake_upsert
    )

    for module in (
        "app.core.langgraph.agents.planning.nodes",
        "app.core.langgraph.profile.nodes",
        "app.core.langgraph.graph",
    ):
        monkeypatch.setattr(f"{module}.llm_service", _FakeLLM())

    def _build(resolves_to: str | None):
        async def fake_classify(_conversation):
            return IntentDecision(intent="revert", scope=[], changes={})

        async def fake_resolve(_query, _index):
            return resolves_to, "test"

        monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", fake_classify)
        monkeypatch.setattr("app.core.langgraph.graph.resolve_version_id", fake_resolve)

        agent = LangGraphAgent()
        agent._agents = {name: build() for name, build in AGENTS.items()}
        builder = StateGraph(RootState)
        _add_nodes(builder, agent)
        builder.set_entry_point("classify")
        graph = builder.compile(checkpointer=MemorySaver(), name="revert-test")

        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "metadata": {"user_id": "1"},
        }
        return graph, config, calls, stored

    return _build


async def _start(graph, config, **extra) -> dict:
    """Run a revert turn up to wherever it stops."""
    await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "go back to the original plan"}],
            "plan": _plan(3, "current"),
            "macros": {"kcal": 2000, "tdee": 2500},
            "current_version_id": "v3-id",
            **extra,
        },
        config,
    )
    return await _state(graph, config)


async def _state(graph, config) -> dict:
    """Return the thread's state merged over the declared defaults."""
    return dict(_DEFAULTS) | (await graph.aget_state(config)).values


async def _resume(graph, config, reply: str) -> dict:
    """Answer a pending interrupt the way the API does."""
    await graph.ainvoke(Command(resume=reply), config)
    return await _state(graph, config)


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------


async def test_revert_stops_at_the_confirm_gate(pipeline):
    """A restore overwrites an approved plan, so it asks first."""
    graph, config, calls, _stored = pipeline("v1-id")
    await _start(graph, config)

    snapshot = await graph.aget_state(config)
    assert snapshot.tasks and snapshot.tasks[0].interrupts
    assert calls["versions"] == [], "a version was written before the user agreed"


async def test_restoring_appends_a_new_version(pipeline):
    """Restore v1 creates v4 with v1's content — it does not rewind.

    The intermediate versions must survive, or the user cannot undo the undo.
    """
    graph, config, calls, stored = pipeline("v1-id")
    await _start(graph, config)
    values = await _resume(graph, config, "yes")

    assert len(calls["versions"]) == 1
    saved = calls["versions"][0]
    assert saved["restored_from"] == "v1-id", "the restore source was not recorded"
    assert saved["parent_id"] == "v3-id", "the superseded version was not recorded"

    # Nothing was deleted or rewritten.
    assert set(stored) == {"v1-id", "v2-id", "v3-id"}
    assert values["plan"]["days"][0]["name"].startswith("v1")


async def test_the_restored_plan_is_reverified(pipeline):
    """A plan that was valid when saved may not be valid for the user now."""
    graph, config, _calls, _stored = pipeline("v1-id")
    values = await _start(graph, config)

    assert values["verdict"] is not None, "the verifiers did not run on the restored plan"
    assert values["computed_macros"] is not None, "macros were not recomputed"


async def test_the_answer_says_whether_the_old_checks_still_apply(pipeline):
    """The user is told why it was re-checked, not just that it was."""
    graph, config, _calls, _stored = pipeline("v1-id")
    values = await _start(graph, config)

    notes = [i for i in values["issues"] if i["rubric_ref"] == "versions.restore"]
    assert len(notes) == 1
    assert "changed" in notes[0]["message"], (
        "a stale profile hash must be reported, not silently ignored"
    )


async def test_declining_a_restore_keeps_the_current_plan(pipeline):
    """Backing out must leave the user exactly where they were."""
    graph, config, calls, _stored = pipeline("v1-id")
    before = await _start(graph, config)
    values = await _resume(graph, config, "no")

    assert calls["versions"] == []
    assert values["plan"] == before["plan"]
    assert values["plan"]["days"][0]["name"].startswith("current")


# ---------------------------------------------------------------------------
# Ambiguity
# ---------------------------------------------------------------------------


async def test_an_ambiguous_request_lists_the_versions(pipeline):
    """Ask rather than guess — a wrong restore costs the current plan."""
    graph, config, calls, _stored = pipeline(None)
    values = await _start(graph, config)

    assert calls["versions"] == []
    assert values["draft_plan"] is None
    assert "v1" in values["answer"] and "v2" in values["answer"]


async def test_a_missing_version_is_reported(pipeline):
    """A version deleted between listing and loading must not crash the turn."""
    graph, config, calls, _stored = pipeline("gone-id")
    values = await _start(graph, config)

    assert calls["versions"] == []
    assert "couldn't find" in values["answer"]


# ---------------------------------------------------------------------------
# resolve_version_id in isolation
# ---------------------------------------------------------------------------


async def test_resolver_rejects_an_id_it_invented(monkeypatch):
    """A hallucinated id must never reach a database lookup."""

    class _Inventing:
        async def call(self, _m, *_a, **_k):
            return VersionChoice(version_id="not-a-real-id", reason="made up")

    monkeypatch.setattr("app.core.langgraph.versioning.llm_service", _Inventing())
    version_id, _reason = await resolve_version_id("the old one", _REF)
    assert version_id is None


async def test_resolver_declines_the_current_version(monkeypatch):
    """Restoring the plan you already have is a no-op, not a new version."""

    class _PicksCurrent:
        async def call(self, _m, *_a, **_k):
            return VersionChoice(version_id="v3-id", reason="the newest")

    monkeypatch.setattr("app.core.langgraph.versioning.llm_service", _PicksCurrent())
    version_id, reason = await resolve_version_id("go back", _REF)
    assert version_id is None
    assert "already have" in reason


async def test_resolver_returns_none_with_no_history():
    """Nothing to restore is not an error."""
    assert await resolve_version_id("go back", []) == (None, "no saved versions")
    assert (await resolve_version_id("go back", _REF[:1]))[0] is None


async def test_resolver_degrades_when_the_model_fails(monkeypatch):
    """A model failure must ask the user, never pick arbitrarily."""

    class _Broken:
        async def call(self, _m, *_a, **_k):
            raise RuntimeError("unavailable")

    monkeypatch.setattr("app.core.langgraph.versioning.llm_service", _Broken())
    version_id, _reason = await resolve_version_id("the original", _REF)
    assert version_id is None


def test_render_versions_marks_the_current_one():
    """The user must be able to tell which plan they are on."""
    rendered = render_versions(_REF)
    assert "(current)" in rendered.splitlines()[0]
    assert rendered.count("(current)") == 1


def test_verification_reason_distinguishes_a_moved_profile():
    """The two cases must read differently, or the note tells the user nothing."""
    same = describe_verification_reason("abc", "abc")
    moved = describe_verification_reason("abc", "xyz")
    assert "unchanged" in same
    assert "changed" in moved and "again" in moved
