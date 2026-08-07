"""Tests for the change_plan branch and the confirm gate.

The confirm gate is the only place in this system where the graph stops
mid-request and waits for a person. The properties worth pinning down are
therefore about what happens *while it is stopped*:

* the stored plan is untouched until the user says yes (§10)
* declining leaves it untouched permanently
* the answer resumes the paused run rather than starting a new one — otherwise
  the plan the user approves is not the plan they were shown
* a change re-runs macros and every verifier, because an added session moves
  TDEE and breaks a deficit that was correct before (§9.2)
"""

import json
import uuid
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.planning.patch import patch_plan
from app.core.langgraph.agents.planning.state import ExerciseChoices
from app.core.langgraph.diff import build_diff
from app.core.langgraph.graph import (
    CONFIRM_REQUIRED_INTENTS,
    LangGraphAgent,
    _add_nodes,
    _is_affirmative,
)
from app.schemas.graph import IntentDecision, ProfileExtraction, RootState
from tests.seed import CONTRAINDICATIONS

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
    name: (field.default_factory() if field.default_factory else field.default)
    for name, field in RootState.model_fields.items()
}


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture(scope="module")
def approved_plan(catalog) -> dict:
    """A 4-day plan standing in for one the user already accepted."""
    plan, issues = patch_plan({"days": []}, {}, PROFILE, catalog)
    # patch_plan refuses an empty plan, so build the fixture directly.
    from app.services.catalog import candidates_for_slot
    from app.services.templates import iter_slots
    from tests.seed import TEMPLATES

    template = TEMPLATES["upper_lower_4day"]
    by_day: dict[str, list[dict]] = {}
    for slot in iter_slots(template):
        candidates = candidates_for_slot(slot, PROFILE, catalog, set(), set())
        if not candidates:
            continue
        exercise = candidates[0]
        by_day.setdefault(slot["day_name"], []).append(
            {
                "slot_id": slot["slot_id"],
                "exercise_id": exercise["exercise_id"],
                "name": exercise["name"],
                "sets": slot["sets"],
                "reps": slot["reps"],
                "rir": slot["rir"],
            }
        )
    return {
        "template_id": "upper_lower_4day",
        "days": [
            {"name": day["name"], "exercises": by_day[day["name"]]}
            for day in template["days"]
            if day["name"] in by_day
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
        return AIMessage(content="Done.")


@pytest.fixture
def pipeline(monkeypatch, catalog, approved_plan):
    """Compile the root graph with storage and every model boundary stubbed."""
    calls: dict[str, list] = {"versions": []}

    monkeypatch.setattr("app.core.langgraph.graph.load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr("app.services.catalog.load_catalog", lambda *a, **k: catalog)

    async def fake_insert_version(**kwargs):
        calls["versions"].append(kwargs)
        return {"version_id": "v-new", "label": "v2", "created_at": "2026-08-05T00:00:00"}

    async def fake_version_index(_user_id):
        return []

    async def fake_get_profile(_user_id):
        return dict(PROFILE)

    async def fake_upsert(_user_id, _profile):
        return None

    monkeypatch.setattr("app.core.langgraph.graph.insert_version", fake_insert_version)
    monkeypatch.setattr("app.core.langgraph.graph.version_index", fake_version_index)
    monkeypatch.setattr(
        "app.core.langgraph.profile.nodes.profile_service.get_profile", fake_get_profile
    )
    monkeypatch.setattr(
        "app.core.langgraph.profile.nodes.profile_service.upsert_profile", fake_upsert
    )

    for module in (
        "app.core.langgraph.agents.planning.nodes",
        "app.core.langgraph.profile.nodes",
        "app.core.langgraph.graph",
    ):
        monkeypatch.setattr(f"{module}.llm_service", _FakeLLM())

    def _build(changes: dict):
        async def fake_classify(_conversation):
            return IntentDecision(intent="change_plan", scope=[], changes=changes)

        monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", fake_classify)

        agent = LangGraphAgent()
        agent._agents = {name: build() for name, build in AGENTS.items()}
        builder = StateGraph(RootState)
        _add_nodes(builder, agent)
        builder.set_entry_point("classify")
        graph = builder.compile(checkpointer=MemorySaver(), name="change-test")

        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "metadata": {"user_id": "1"},
        }
        return graph, config, calls

    return _build


async def _start(graph, config, approved_plan, text="make it 5 days", **extra):
    """Run a change turn up to wherever it stops, and return the state.

    ``extra`` seeds additional state on the first invoke. Seeding rather than
    calling ``aupdate_state`` later matters: writing to a thread that is parked
    at an interrupt disturbs the pending task, and the resume then finds nothing
    to resume.
    """
    await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": text}],
            "plan": approved_plan,
            "macros": {"kcal": 2000, "tdee": 2500, "protein_g": 150, "fat_g": 60, "carbs_g": 210},
            **extra,
        },
        config,
    )
    return await _state(graph, config)


async def _state(graph, config) -> dict:
    """Return the thread's state merged over the declared defaults."""
    snapshot = await graph.aget_state(config)
    return dict(_DEFAULTS) | snapshot.values


async def _resume(graph, config, reply: str):
    """Answer a pending interrupt through the same path the API uses."""
    from langgraph.types import Command

    await graph.ainvoke(Command(resume=reply), config)
    return await _state(graph, config)


# ---------------------------------------------------------------------------
# The gate stops
# ---------------------------------------------------------------------------


async def test_a_change_stops_at_the_confirm_gate(pipeline, approved_plan):
    """§10: a change overwrites an approved plan, so it must ask first."""
    graph, config, calls = pipeline({"days": 3})
    await _start(graph, config, approved_plan)

    snapshot = await graph.aget_state(config)
    assert snapshot.next, "the graph ran to completion instead of stopping"
    assert snapshot.tasks[0].interrupts, "no interrupt was raised"

    payload = snapshot.tasks[0].interrupts[0].value
    assert payload["type"] == "confirm_change"
    assert "4 → 3 sessions" in payload["question"]
    assert calls["versions"] == [], "a version was written before the user agreed"


async def test_the_stored_plan_is_untouched_while_paused(pipeline, approved_plan):
    """The plan the user has must not change just because a change was proposed."""
    graph, config, _calls = pipeline({"days": 3})
    values = await _start(graph, config, approved_plan)

    assert values["plan"] == approved_plan
    assert values["draft_plan"] != approved_plan, "nothing was actually drafted"
    assert values["pending_commit"] is not None


async def test_the_diff_is_shown_against_the_current_plan(pipeline, approved_plan):
    """§9.5: the user is being told what they are about to lose."""
    graph, config, _calls = pipeline({"days": 3})
    values = await _start(graph, config, approved_plan)

    diff = values["pending_commit"]
    assert diff["days_before"] == 4
    assert diff["days_after"] == 3
    assert diff["removed"], "a 4→3 day change must remove something"


# ---------------------------------------------------------------------------
# Declining
# ---------------------------------------------------------------------------


async def test_declining_leaves_the_plan_alone(pipeline, approved_plan):
    """A "no" must be final, and must not half-apply the change."""
    graph, config, calls = pipeline({"days": 3})
    await _start(graph, config, approved_plan)
    values = await _resume(graph, config, "no thanks")

    assert values["plan"] == approved_plan
    assert values["pending_commit"] is None
    assert calls["versions"] == []
    assert "Nothing has changed" in values["answer"]


@pytest.mark.parametrize("reply", ["no", "not yet", "wait, what does that remove?", ""])
async def test_anything_that_is_not_a_yes_is_a_no(pipeline, approved_plan, reply):
    """An ambiguous reply must not be read as consent."""
    graph, config, calls = pipeline({"days": 3})
    await _start(graph, config, approved_plan)
    values = await _resume(graph, config, reply)

    assert calls["versions"] == [], f"{reply!r} was treated as approval"
    assert values["plan"] == approved_plan


# ---------------------------------------------------------------------------
# Accepting
# ---------------------------------------------------------------------------


async def test_accepting_applies_the_change_and_versions_it(pipeline, approved_plan):
    """A "yes" resumes the same run and commits the plan the user was shown."""
    graph, config, calls = pipeline({"days": 3})
    paused = await _start(graph, config, approved_plan)
    shown = paused["draft_plan"]

    values = await _resume(graph, config, "yes")

    assert len(calls["versions"]) == 1
    assert calls["versions"][0]["plan"] == shown, (
        "the committed plan is not the plan the user approved"
    )
    assert values["plan"] == shown
    assert values["pending_commit"] is None


async def test_the_new_version_records_its_parent(pipeline, approved_plan):
    """§9.5: history is append-only, so an undo has something to return to."""
    graph, config, calls = pipeline({"days": 3})
    await _start(graph, config, approved_plan, current_version_id="v-old")
    await _resume(graph, config, "yes")

    assert calls["versions"][0]["parent_id"] == "v-old"


async def test_macros_are_recomputed_for_the_new_day_count(pipeline, approved_plan):
    """§9.2: an extra session raises TDEE, so the old targets cannot be reused."""
    graph, config, _calls = pipeline({"days": 3})
    values = await _start(graph, config, approved_plan)

    computed = values["computed_macros"]
    assert computed is not None
    assert computed["tdee"] != 2500, "the macros were carried over unchanged"
    assert values["verdict"] is not None, "the verifiers did not run on the new plan"


async def test_the_answer_is_composed_from_this_turn_only(pipeline, approved_plan, monkeypatch):
    """A 4→5 day change was announced to the user as a 4-day plan.

    Two causes, both here. The composer is told to open with the split, the
    sessions a week and the goal, and nothing in its prompt carried them — so it
    took all three from the only other place they appeared, the plan being
    replaced. And ``issues`` accumulated across turns, so the findings backing
    that sentence up still named `Upper A` and `Lower B`.

    Asserted on the prompt rather than the prose: what the composer is *handed*
    is the contract, and the answer itself changes with every prompt edit.
    """
    captured: dict[str, str] = {}

    def spy(**kwargs):
        captured.update(kwargs)
        return "composed"

    monkeypatch.setattr("app.core.langgraph.graph.load_compose_answer_prompt", spy)

    graph, config, _calls = pipeline({"days": 5})
    stale = {
        "source": "volume",
        "severity": "warn",
        "location": "Upper A / vertical push",
        "message": "No vertical push exercise matches your equipment.",
        "suggestion": None,
        "rubric_ref": "catalog.no_candidates",
    }
    await _start(graph, config, approved_plan, issues=[stale])
    values = await _resume(graph, config, "yes")

    assert len(values["plan"]["days"]) == 5, "the fixture no longer exercises a 4→5 change"
    assert "Sessions a week: 5" in captured["plan"]
    assert "Chest / Back / Legs / Upper / Lower, 5 days" in captured["plan"]
    assert "Goal: fat_loss" in captured["plan"]
    assert "Upper A / vertical push" not in captured["issues"], (
        "the previous turn's findings were reported as this turn's"
    )


# ---------------------------------------------------------------------------
# patch_plan in isolation
# ---------------------------------------------------------------------------


def test_patch_keeps_exercises_that_still_fit(catalog, approved_plan):
    """A change must read as an adjustment, not as a different programme."""
    draft, _issues = patch_plan(approved_plan, {"days": 3}, PROFILE, catalog)

    before = {e["exercise_id"] for d in approved_plan["days"] for e in d["exercises"]}
    after = {e["exercise_id"] for d in draft["days"] for e in d["exercises"]}
    assert after & before, "the patch discarded every exercise the user had"


def test_patch_rechecks_carried_exercises_against_new_injuries(catalog, approved_plan):
    """An injury declared since the plan was approved must not survive the patch."""
    injured = {**PROFILE, "injuries": ["knee_pain_patellofemoral"]}
    draft, _issues = patch_plan(approved_plan, {"days": 3}, injured, catalog)

    forbidden = set(
        CONTRAINDICATIONS["injuries"]["knee_pain_patellofemoral"]["avoid_joint_actions"]
    )
    for day in draft["days"]:
        for exercise in day["exercises"]:
            meta = catalog[exercise["exercise_id"]]
            assert not set(meta["joint_actions"]) & forbidden, (
                f"{exercise['exercise_id']} was carried forward despite the injury"
            )


def test_patch_reports_an_unsupported_change(catalog, approved_plan):
    """A change we cannot apply is said out loud, not silently ignored."""
    draft, issues = patch_plan(approved_plan, {"tempo": "slow"}, PROFILE, catalog)

    assert draft is None
    assert [i["severity"] for i in issues] == ["block"]
    assert issues[0]["rubric_ref"] == "change.unsupported"


def test_patch_refuses_when_there_is_no_plan(catalog):
    """Changing nothing is a mistake worth naming."""
    draft, issues = patch_plan({}, {"days": 5}, PROFILE, catalog)

    assert draft is None
    assert issues[0]["rubric_ref"] == "change.no_plan"


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def test_confirm_required_matches_the_workflow_table():
    """§10: writes over approved work confirm; reads never do."""
    assert CONFIRM_REQUIRED_INTENTS == {"change_plan", "revert"}


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("yes", True),
        ("Yes.", True),
        ("ok", True),
        ("go ahead", True),
        ("yes please", True),
        ("no", False),
        ("", False),
        ("not right now", False),
        ("yes but can you also change the goal?", False),
        (None, False),
    ],
)
def test_affirmative_detection_defaults_to_no(reply, expected):
    """Only a recognised yes counts. A long reply is prose, not consent."""
    assert _is_affirmative(reply) is expected


def test_diff_reports_no_change_honestly():
    """An identical plan must not be dressed up as an adjustment."""
    plan = {"days": [{"name": "A", "exercises": [{"name": "Squat"}]}]}
    diff = build_diff(plan, plan, {"kcal": 2000}, {"kcal": 2000})

    assert diff["added"] == []
    assert diff["removed"] == []
    assert "Nothing" in diff["summary"]
