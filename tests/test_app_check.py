"""Tests for the check branch — reviewing a plan the user pasted in.

Two failures define this branch, and both are silent:

**Overwriting the user's own plan.** They pasted someone else's programme to ask
an opinion. Writing it to ``plan`` replaces what they actually follow with what
they were merely curious about (``docs/workflow.md`` §2.3, §9.3).

**Guessing an exercise name.** Reading "leg press" as "leg extension" does not
produce a slightly-wrong review — it produces a confident review of a plan the
user is not doing, in which the injury check cleared a movement they never
perform (§5.2, §12).
"""

import json
import uuid
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.ingest.state import ParsedDay, ParsedExercise, ParsedPlan
from app.core.langgraph.agents.planning.state import ExerciseChoices
from app.core.langgraph.graph import READ_ONLY_INTENTS, LangGraphAgent, _add_nodes
from app.schemas.graph import IntentDecision, ProfileExtraction, RootState
from app.services.exercise_resolver import (
    CONFIDENCE_THRESHOLD,
    normalise,
    resolve_exercise,
)

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

OWN_PLAN = {
    "template_id": "upper_lower_4day",
    "days": [
        {
            "name": "My day",
            "exercises": [
                {
                    "slot_id": "s0",
                    "exercise_id": "back_squat",
                    "name": "Back Squat",
                    "sets": 4,
                    "reps": [5, 8],
                    "rir": [1, 2],
                }
            ],
        }
    ],
}


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


def _parsed(*lines: tuple[str, int | None, list[int] | None]) -> ParsedPlan:
    """Build the parser's output from ``(name, sets, reps)`` tuples."""
    return ParsedPlan(
        is_a_plan=True,
        days=[
            ParsedDay(
                name="Pasted day",
                exercises=[
                    ParsedExercise(raw_name=name, sets=sets, reps=reps)
                    for name, sets, reps in lines
                ],
            )
        ],
    )


@pytest.fixture
def pipeline(monkeypatch, catalog):
    """Compile the root graph with storage and every model boundary stubbed."""
    calls: dict[str, list] = {"versions": []}

    monkeypatch.setattr("app.core.langgraph.graph.load_catalog", lambda *a, **k: catalog)

    async def fake_insert_version(**kwargs):
        calls["versions"].append(kwargs)
        return {"version_id": "v", "label": "v1", "created_at": "2026-08-05T00:00:00"}

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

    def _build(parsed: ParsedPlan, scope: list[str] | None = None):
        class _FakeLLM:
            """Per-module stand-in for the shared llm_service singleton."""

            def bind_tools(self, _tools):
                return self

            async def call(self, _messages, *_a, **kwargs):
                fmt = kwargs.get("response_format")
                if fmt is ParsedPlan:
                    return parsed
                if fmt is ProfileExtraction:
                    return ProfileExtraction()
                if fmt is ExerciseChoices:
                    return ExerciseChoices(choices=[])
                if fmt is not None:
                    return fmt()
                return AIMessage(content="Here's my read on that plan.")

        for module in (
            "app.core.langgraph.agents.qa.nodes",
            "app.core.langgraph.agents.planning.nodes",
            "app.core.langgraph.profile.nodes",
            "app.core.langgraph.agents.ingest.nodes",
            "app.core.langgraph.graph",
        ):
            monkeypatch.setattr(f"{module}.llm_service", _FakeLLM())

        async def fake_classify(_conversation):
            return IntentDecision(intent="check", scope=scope or [], changes={})

        monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", fake_classify)

        agent = LangGraphAgent()
        agent._agents = {name: build() for name, build in AGENTS.items()}
        builder = StateGraph(RootState)
        _add_nodes(builder, agent)
        builder.set_entry_point("classify")
        graph = builder.compile(checkpointer=MemorySaver(), name="check-test")

        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "metadata": {"user_id": "1"},
        }
        return graph, config, calls

    return _build


async def _run(graph, config, text="what do you think of this plan?") -> dict:
    """Run a check turn and return the final state."""
    await graph.ainvoke({"messages": [{"role": "user", "content": text}], "plan": OWN_PLAN}, config)
    return dict(_DEFAULTS) | (await graph.aget_state(config)).values


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------


async def test_a_pasted_plan_never_becomes_the_users_plan(pipeline):
    """§2.3: the plan they follow must survive asking about someone else's."""
    graph, config, calls = pipeline(_parsed(("Barbell Bench Press", 4, [6, 8])))
    values = await _run(graph, config)

    assert values["submitted_plan"] is not None, "nothing was ingested"
    assert values["plan"] == OWN_PLAN, "the pasted plan overwrote the stored one"
    assert values["draft_plan"] is None
    assert calls["versions"] == [], "a review created a version"


def test_check_is_declared_read_only():
    """The routing constant and the branch behaviour must agree."""
    assert "check" in READ_ONLY_INTENTS


async def test_a_pasted_plan_is_reviewed(pipeline):
    """The point of the branch: findings, not silence."""
    graph, config, _calls = pipeline(
        _parsed(("Barbell Bench Press", 8, [6, 8]), ("Back Squat", 8, [5, 8]))
    )
    values = await _run(graph, config)

    assert values["verdict"] in {"pass", "warn", "fail"}
    assert values["answer"]


async def test_scope_narrows_which_verifiers_run(pipeline):
    """§9.3: only a check turn lets the user's wording pick the checks."""
    graph, config, _calls = pipeline(_parsed(("Back Squat", 8, [5, 8])), scope=["injury"])
    values = await _run(graph, config, "my knee hurts, is this plan ok?")

    sources = {issue["source"] for issue in values["issues"] if issue["source"] != "volume"}
    assert "macro" not in sources, "a macro check ran for an injury-scoped request"


# ---------------------------------------------------------------------------
# Refusing to guess
# ---------------------------------------------------------------------------


async def test_an_unrecognised_exercise_is_reported_not_guessed(pipeline):
    """§12: a low-confidence name is a question, never a nearest match."""
    graph, config, _calls = pipeline(
        _parsed(("Zercher good morning off pins", 3, [8, 10]), ("Back Squat", 4, [5, 8]))
    )
    values = await _run(graph, config)

    unresolved = [i for i in values["issues"] if i["rubric_ref"] == "ingest.unresolved_exercise"]
    assert len(unresolved) == 1
    assert "Zercher" in unresolved[0]["location"]

    reviewed = {
        exercise["exercise_id"]
        for day in (values["submitted_plan"] or {}).get("days", [])
        for exercise in day["exercises"]
    }
    assert reviewed == {"back_squat"}, "an unidentified line was silently included"


async def test_a_line_without_sets_is_excluded_and_reported(pipeline):
    """Assuming a typical set count puts invented volume into a real review."""
    graph, config, _calls = pipeline(
        _parsed(("Barbell Bench Press", None, None), ("Back Squat", 4, [5, 8]))
    )
    values = await _run(graph, config)

    missing = [i for i in values["issues"] if i["rubric_ref"] == "ingest.missing_prescription"]
    assert len(missing) == 1

    reviewed = {
        exercise["exercise_id"]
        for day in (values["submitted_plan"] or {}).get("days", [])
        for exercise in day["exercises"]
    }
    assert "barbell_bench_press" not in reviewed


async def test_no_plan_in_the_message_asks_for_one(pipeline):
    """A question about training is not a plan to assess."""
    graph, config, calls = pipeline(ParsedPlan(is_a_plan=False, days=[]))
    values = await _run(graph, config, "should I train fasted?")

    assert values["submitted_plan"] is None
    assert calls["versions"] == []
    assert "couldn't find a training plan" in values["answer"]


async def test_a_wholly_unreadable_plan_asks_rather_than_reviews(pipeline):
    """If nothing could be identified there is nothing honest to say about it."""
    graph, config, _calls = pipeline(
        _parsed(("qqq zzz wwww", 3, [8, 10]), ("xyzzy plugh", 3, [8, 10]))
    )
    values = await _run(graph, config)

    assert values["verdict"] is None, "a verdict was produced from nothing"
    assert "couldn't read" in values["answer"]


# ---------------------------------------------------------------------------
# resolve_exercise in isolation
# ---------------------------------------------------------------------------


def test_exact_name_resolves_with_full_confidence(catalog):
    """The common case must not go near fuzzy matching."""
    result = resolve_exercise("Barbell Bench Press", catalog)
    assert result["exercise_id"] == "barbell_bench_press"
    assert result["confidence"] == 1.0


def test_shorthand_resolves(catalog):
    """Users type "db", not "dumbbell"."""
    assert resolve_exercise("db shoulder press", catalog)["exercise_id"] == (
        "dumbbell_shoulder_press"
    )


def test_word_order_does_not_matter(catalog):
    """ "bench press barbell" is the same exercise as "Barbell Bench Press"."""
    assert resolve_exercise("bench press barbell", catalog)["exercise_id"] == (
        "barbell_bench_press"
    )


def test_an_ambiguous_name_returns_candidates_not_a_pick(catalog):
    """Several plausible matches means the user chooses, not the resolver."""
    result = resolve_exercise("press", catalog)
    assert result["exercise_id"] is None
    assert result["candidates"]


def test_leg_press_never_resolves_to_leg_extension(catalog):
    """The named failure from §5.2 — it changes what the injury check assesses."""
    result = resolve_exercise("leg press", catalog)
    assert result["exercise_id"] != "leg_extension_machine"


def test_nonsense_resolves_to_nothing(catalog):
    """Below the threshold, no id comes back at all."""
    result = resolve_exercise("qwertyuiop asdfgh", catalog)
    assert result["exercise_id"] is None
    assert result["confidence"] < CONFIDENCE_THRESHOLD


def test_empty_input_is_safe(catalog):
    """A blank line must not match the first catalog entry."""
    assert resolve_exercise("", catalog)["exercise_id"] is None


def test_normalise_strips_punctuation_and_case():
    """Matching happens on comparable text."""
    assert normalise("Incline Bench Press (Wide Grip)") == "incline bench press wide grip"
