"""End-to-end tests for the build_plan pipeline.

The whole root graph, compiled with ``MemorySaver`` and every LLM boundary
stubbed. No Postgres: profile loading, profile saving and version insertion are
patched, so these tests assert graph behaviour rather than storage.

The properties are the ones that keep the design honest:

* an incomplete profile reaches ``ask_missing`` and never reaches ``planning``
* ``calc_macro`` cannot be bypassed on the way from a plan to an answer
* a failing verdict repairs at most twice, then answers anyway
* the repairer never receives the conversation
* a composer failure loses the prose, not the plan
"""

import json
import uuid
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.planning.state import ExerciseChoices
from app.core.langgraph.graph import LangGraphAgent, _add_nodes
from app.core.langgraph.templates import TEMPLATES, iter_slots
from app.schemas.graph import Intent, IntentDecision, Issue, ProfileExtraction, RootState

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_seed.json"

pytestmark = pytest.mark.skipif(
    not _CATALOG_FILE.exists(),
    reason="data/exercise_seed.json is missing — the catalog fixture needs it",
)

COMPLETE_PROFILE = {
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


@pytest.fixture
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture
def pipeline(monkeypatch, catalog):
    """Build the root graph with every external boundary stubbed.

    Returns a factory taking the stored profile and the intent, and returning
    ``(graph, config, calls)`` where ``calls`` records what each stub saw.
    """
    calls: dict[str, list] = {"versions": [], "saved_profiles": [], "repair_kwargs": []}

    monkeypatch.setattr("app.services.catalog.load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr("app.core.langgraph.graph.load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.nodes.candidates_for_slot.__module__",
        "app.services.catalog",
        raising=False,
    )

    async def fake_insert_version(**kwargs):
        calls["versions"].append(kwargs)
        return {"version_id": "v-test", "label": "v1", "created_at": "2026-08-05T00:00:00"}

    async def fake_version_index(_user_id):
        return [{"version_id": "v-test", "label": "v1", "created_at": "2026-08-05T00:00:00"}]

    monkeypatch.setattr("app.core.langgraph.graph.insert_version", fake_insert_version)
    monkeypatch.setattr("app.core.langgraph.graph.version_index", fake_version_index)

    async def fake_upsert(user_id, profile):
        calls["saved_profiles"].append((user_id, profile))

    monkeypatch.setattr(
        "app.core.langgraph.profile.nodes.profile_service.upsert_profile", fake_upsert
    )

    def _build(stored_profile: dict, intent: Intent = "build_plan", extraction=None):
        async def fake_get_profile(_user_id):
            return dict(stored_profile)

        monkeypatch.setattr(
            "app.core.langgraph.profile.nodes.profile_service.get_profile",
            fake_get_profile,
        )

        async def fake_classify(_conversation):
            return IntentDecision(intent=intent, scope=[], changes={})

        monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", fake_classify)

        class _FakeLLM:
            """Per-module stand-in for the shared llm_service singleton.

            Replacing the module-level *name* rather than patching
            ``llm_service.call``: the service is a singleton, so patching its
            attribute through several module paths mutates one object, and any
            module left unpatched reaches the network.
            """

            def bind_tools(self, _tools):
                return self

            async def call(self, _messages, *_a, **kwargs):
                fmt = kwargs.get("response_format")
                if fmt is ProfileExtraction:
                    return extraction or ProfileExtraction()
                if fmt is ExerciseChoices:
                    return ExerciseChoices(choices=[])
                if fmt is not None:
                    return fmt()
                return AIMessage(content="Here is your plan.")

        for module in (
            "app.core.langgraph.profile.nodes",
            "app.core.langgraph.agents.planning.nodes",
            "app.core.langgraph.agents.ingest.nodes",
            "app.core.langgraph.graph",
        ):
            monkeypatch.setattr(f"{module}.llm_service", _FakeLLM())

        agent = LangGraphAgent()
        agent._agents = {name: build() for name, build in AGENTS.items()}
        builder = StateGraph(RootState)
        _add_nodes(builder, agent)
        builder.set_entry_point("classify")
        graph = builder.compile(checkpointer=MemorySaver(), name="root-test")

        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "metadata": {"user_id": "1"},
        }
        return graph, config, calls, agent

    return _build


async def _run(graph, config, text: str = "build me a plan") -> dict:
    """Invoke the graph once and return the final state, defaults included.

    ``aget_state().values`` carries only the channels a run actually wrote, so a
    field no node touched is absent rather than holding its declared default.
    Merging over the defaults here keeps the assertions about what the pipeline
    produced, not about which channels it happened to write.
    """
    await graph.ainvoke({"messages": [{"role": "user", "content": text}]}, config)
    written = (await graph.aget_state(config)).values
    return {field: default for field, default in _DEFAULTS.items()} | written


_DEFAULTS = {
    name: (field.default_factory() if field.default_factory else field.default)
    for name, field in RootState.model_fields.items()
}


# ---------------------------------------------------------------------------
# The profile gate
# ---------------------------------------------------------------------------


async def test_an_empty_profile_asks_for_everything_at_once(pipeline):
    """§9.1: one question covering every missing field, not one field per turn."""
    graph, config, _calls, _agent = pipeline({})
    values = await _run(graph, config)

    assert values["draft_plan"] is None, "a plan was built without a profile"
    assert len(values["missing_fields"]) == 9
    # One message, listing every field.
    assert values["answer"].count("\n- ") == 9


async def test_a_partial_profile_asks_only_for_the_rest(pipeline):
    """Fields already known must not be asked for again."""
    partial = {k: v for k, v in COMPLETE_PROFILE.items() if k not in {"age", "goal"}}
    graph, config, _calls, _agent = pipeline(partial)
    values = await _run(graph, config)

    assert set(values["missing_fields"]) == {"age", "goal"}
    assert values["draft_plan"] is None


async def test_no_injuries_is_a_complete_answer(pipeline):
    """An empty injury list means "I have none" — not an unanswered field."""
    graph, config, _calls, _agent = pipeline({**COMPLETE_PROFILE, "injuries": []})
    values = await _run(graph, config)

    assert values["missing_fields"] == []
    assert values["draft_plan"] is not None


async def test_facts_stated_this_turn_complete_the_profile(pipeline):
    """extract_profile runs every turn and merges over what is stored."""
    stored = {k: v for k, v in COMPLETE_PROFILE.items() if k != "weight_kg"}
    graph, config, calls, _agent = pipeline(stored, extraction=ProfileExtraction(weight_kg=75.0))
    values = await _run(graph, config, "I weigh 75kg")

    assert values["missing_fields"] == []
    assert values["profile"]["weight_kg"] == 75.0
    assert calls["saved_profiles"], "a newly stated fact was not persisted"


# ---------------------------------------------------------------------------
# The build pipeline
# ---------------------------------------------------------------------------


async def test_a_complete_profile_produces_a_plan_with_macros(pipeline):
    """The happy path: plan, macros and a verdict, all in one turn."""
    graph, config, calls, _agent = pipeline(COMPLETE_PROFILE)
    values = await _run(graph, config)

    plan = values["draft_plan"]
    assert plan is not None
    assert len(plan["days"]) == 4

    macros = values["computed_macros"]
    assert macros["kcal"] < macros["tdee"], "a fat-loss goal must set a deficit"
    assert values["verdict"] in {"pass", "warn", "fail"}
    assert values["answer"]


async def test_macros_cannot_be_bypassed(pipeline):
    """calc_macro is the bottleneck: no plan reaches an answer without it.

    §9.2 depends on this — if a plan could skip the macro step, a modified plan
    would keep stale targets and the deficit would silently break.
    """
    graph, config, _calls, _agent = pipeline(COMPLETE_PROFILE)
    values = await _run(graph, config)

    assert values["draft_plan"] is not None
    assert values["computed_macros"] is not None
    assert values["computed_macros"]["tdee"] > 0


async def test_the_plan_is_snapshotted_once(pipeline):
    """Exactly one version row per successful build, carrying the rubric version."""
    graph, config, calls, _agent = pipeline(COMPLETE_PROFILE)
    values = await _run(graph, config)

    assert len(calls["versions"]) == 1
    saved = calls["versions"][0]
    assert saved["plan"] == values["draft_plan"]
    assert saved["rubric_version"]
    assert saved["profile_hash"]
    assert values["plan"] == values["draft_plan"]


async def test_prescriptions_survive_the_whole_pipeline(pipeline):
    """§1.1: the numbers in the answer are the template's, end to end."""
    graph, config, _calls, _agent = pipeline(COMPLETE_PROFILE)
    values = await _run(graph, config)

    slots = {s["slot_id"]: s for s in iter_slots(TEMPLATES["upper_lower_4day"])}
    for day in values["draft_plan"]["days"]:
        for exercise in day["exercises"]:
            slot = slots[exercise["slot_id"]]
            assert (exercise["sets"], exercise["reps"], exercise["rir"]) == (
                slot["sets"],
                slot["reps"],
                slot["rir"],
            )


# ---------------------------------------------------------------------------
# The repair loop
# ---------------------------------------------------------------------------


def _blocking_issue() -> Issue:
    """An issue severe enough to trigger a repair."""
    return Issue(
        source="injury",
        severity="block",
        location="Nowhere / nothing",
        message="synthetic blocking issue",
        suggestion=None,
        rubric_ref="test.block",
    )


async def test_repair_is_capped_and_still_answers(pipeline, monkeypatch):
    """§8: two attempts, then the issue list goes to the user rather than looping."""
    seen: list[int] = []

    async def always_fail(state, config):
        from langgraph.types import Command

        seen.append(state.repair_count)
        return Command(
            update={"issues": [_blocking_issue()], "verdict": "fail"}, goto="verdict_gate"
        )

    graph, config, _calls, agent = pipeline(COMPLETE_PROFILE)
    monkeypatch.setattr(agent, "_verification", always_fail)

    # Rebuild with the patched node bound in.
    builder = StateGraph(RootState)
    _add_nodes(builder, agent)
    builder.set_entry_point("classify")
    graph = builder.compile(checkpointer=MemorySaver(), name="root-repair-test")

    values = await _run(graph, config)

    assert values["repair_count"] <= 2, "the repair loop exceeded its cap"
    assert values["verdict"] == "fail"
    assert values["answer"], "an exhausted repair budget must still answer"


async def test_a_failed_plan_is_not_snapshotted(pipeline, monkeypatch):
    """A plan that never passed must not become the user's stored plan."""

    async def always_fail(state, config):
        from langgraph.types import Command

        return Command(
            update={"issues": [_blocking_issue()], "verdict": "fail"}, goto="verdict_gate"
        )

    graph, config, calls, agent = pipeline(COMPLETE_PROFILE)
    monkeypatch.setattr(agent, "_verification", always_fail)
    builder = StateGraph(RootState)
    _add_nodes(builder, agent)
    builder.set_entry_point("classify")
    graph = builder.compile(checkpointer=MemorySaver(), name="root-nosnap-test")

    values = await _run(graph, config)

    assert calls["versions"] == [], "a failing plan was persisted"
    assert values["plan"] is None


def test_repair_cannot_see_the_conversation():
    """§8: enforced by the signature, not by a comment."""
    import inspect

    from app.core.langgraph.agents.planning.repair import repair_plan

    assert "messages" not in inspect.signature(repair_plan).parameters


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


async def test_a_composer_failure_still_returns_the_plan(pipeline, monkeypatch):
    """Losing the prose step must not lose work that is already computed."""
    graph, config, _calls, agent = pipeline(COMPLETE_PROFILE)

    async def exploding(*_a, **kwargs):
        if kwargs.get("response_format") is ProfileExtraction:
            return ProfileExtraction()
        if kwargs.get("response_format") is ExerciseChoices:
            return ExerciseChoices(choices=[])
        raise RuntimeError("composer unavailable")

    monkeypatch.setattr("app.core.langgraph.graph.llm_service.call", exploding)

    values = await _run(graph, config)

    assert values["draft_plan"] is not None
    assert values["answer"], "the fallback rendering produced nothing"
    assert "kcal" in values["answer"], "the fallback lost the macro targets"


def test_every_declared_intent_has_a_real_branch():
    """The not_implemented fallback must be unreachable for any declared intent.

    It stays in the graph as a guard for an Intent literal added without a
    branch — that must answer honestly rather than fall through to whichever
    node happens to be next.
    """
    from app.core.langgraph.graph import CONFIRM_REQUIRED_INTENTS, READ_ONLY_INTENTS
    from app.core.langgraph.routing.dispatch import DISPATCH_TARGETS

    handled = {"build_plan", "change_plan", "revert", "check", "general_qa", "off_topic"}
    assert set(DISPATCH_TARGETS) == handled
    assert CONFIRM_REQUIRED_INTENTS <= handled
    assert READ_ONLY_INTENTS <= handled


async def test_general_qa_never_touches_the_profile_nodes(pipeline):
    """A knowledge question must not be asked for body weight."""
    graph, config, _calls, _agent = pipeline({}, intent="general_qa")
    values = await _run(graph, config, "what is protein?")

    assert values["missing_fields"] == []
    assert values["draft_plan"] is None
    assert values["answer"]
