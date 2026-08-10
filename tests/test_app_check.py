"""Tests for the review agent — assessing a plan the user pasted in.

Two failures define this agent, and both are silent:

**Overwriting the user's own plan.** They pasted someone else's programme to ask
an opinion. Turning that into the plan they follow replaces what they actually
train with what they were merely curious about. Under the supervisor
architecture this is prevented structurally rather than by two state fields:
nothing here mints a ``draft_id``, and ``save_plan`` accepts nothing else.

**Guessing an exercise name.** Reading "leg press" as "leg extension" does not
produce a slightly-wrong review — it produces a confident review of a plan the
user is not doing, in which the injury check cleared a movement they never
perform.
"""

import inspect
import json
import uuid
from pathlib import Path

import pytest

from app.core.langgraph.agents.review.state import ReviewState
from app.core.langgraph.agents.review.tools import lookup_exercise, score_plan
from app.services.exercise_resolver import (
    CONFIDENCE_THRESHOLD,
    normalise,
    resolve_exercise,
)
from tests.support import call, message, updates

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


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture
def scored(monkeypatch):
    """Score every plan as a pass, without a rubric database behind it.

    What ``score_plan`` has to guarantee is that macros were computed and the
    verifiers ran on what was *understood*. Which findings the real rubrics
    produce is ``test_app_verification.py``'s subject.
    """
    seen: list[dict] = []

    async def fake_score(plan, profile, config=None, scope=None):
        seen.append({"plan": plan, "profile": profile, "scope": scope})
        return {"kcal": 2100, "tdee": 2400, "goal": profile.get("goal")}, [], "pass"

    monkeypatch.setattr("app.core.langgraph.agents.review.tools.score", fake_score)
    monkeypatch.setattr("app.core.langgraph.rendering.load_catalog", lambda *a, **k: {})
    return seen


def _state(catalog: dict, **overrides) -> ReviewState:
    """Build a review state the tools can read."""
    return {
        "messages": [],
        "catalog": catalog,
        "profile": dict(PROFILE),
        "submitted_plan": None,
        "unresolved": [],
        "incomplete": [],
        "scored": False,
        **overrides,
    }


def _config() -> dict:
    """A runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _days(*lines: tuple[str, int | None, list[int] | None]) -> list[dict]:
    """Build the model's transcription from ``(name, sets, reps)`` tuples."""
    return [
        {
            "name": "Pasted day",
            "exercises": [
                {"raw_name": name, "sets": sets, "reps": reps} for name, sets, reps in lines
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Read-only, structurally
# ---------------------------------------------------------------------------


async def test_a_review_produces_no_handle_anything_could_be_saved_from(catalog, scored):
    """The absence of a draft_id is what keeps a pasted plan from being adopted."""
    result = await call(
        score_plan, _state(catalog), _config(), days=_days(("Barbell Bench Press", 4, [6, 8]))
    )

    written = updates(result)
    assert written["scored"] is True
    assert "draft_id" not in written
    assert "draft_id" not in message(result).content


def test_the_agent_has_nowhere_to_write_a_plan():
    """Its state carries what was understood, not a plan anything accepts."""
    annotations = ReviewState.__annotations__
    assert "plan" not in annotations
    assert "draft_id" not in annotations
    assert "submitted_plan" in annotations


def test_no_review_tool_can_reach_the_draft_store():
    """A review that could mint a handle would be a review that could be saved."""
    from app.core.langgraph.agents.review import tools as review_tools

    for tool in review_tools.tools:
        source = inspect.getsource(tool.coroutine or tool.func)
        assert "drafts" not in source, f"{tool.name} reaches the draft store"


async def test_a_pasted_plan_is_reviewed(catalog, scored):
    """The point of the agent: findings, not silence."""
    result = await call(
        score_plan,
        _state(catalog),
        _config(),
        days=_days(("Barbell Bench Press", 8, [6, 8]), ("Back Squat", 8, [5, 8])),
    )
    body = json.loads(message(result).content)

    assert body["verdict"] in {"pass", "warn", "fail"}
    assert body["macros"], "a review without macros is a review of nothing"
    assert scored, "the verifiers never ran"


async def test_the_review_assesses_what_was_understood(catalog, scored):
    """The scorer sees resolved catalog ids, never the raw text."""
    await call(
        score_plan, _state(catalog), _config(), days=_days(("db shoulder press", 3, [8, 12]))
    )

    exercises = scored[0]["plan"]["days"][0]["exercises"]
    assert exercises[0]["exercise_id"] == "dumbbell_shoulder_press"
    assert "raw_name" not in exercises[0]


# ---------------------------------------------------------------------------
# Refusing to guess
# ---------------------------------------------------------------------------


async def test_an_unrecognised_exercise_is_reported_not_guessed(catalog, scored):
    """A low-confidence name is a question, never a nearest match."""
    result = await call(
        score_plan,
        _state(catalog),
        _config(),
        days=_days(("Zercher good morning off pins", 3, [8, 10]), ("Back Squat", 4, [5, 8])),
    )

    body = json.loads(message(result).content)
    unresolved = [
        issue for issue in body["issues"] if issue["rubric_ref"] == "ingest.unresolved_exercise"
    ]
    assert len(unresolved) == 1
    assert "Zercher" in unresolved[0]["location"]

    reviewed = {
        exercise["exercise_id"]
        for day in updates(result)["submitted_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert reviewed == {"back_squat"}, "an unidentified line was silently included"


async def test_a_line_without_sets_is_excluded_and_reported(catalog, scored):
    """Assuming a typical set count puts invented volume into a real review."""
    result = await call(
        score_plan,
        _state(catalog),
        _config(),
        days=_days(("Barbell Bench Press", None, None), ("Back Squat", 4, [5, 8])),
    )

    body = json.loads(message(result).content)
    missing = [
        issue for issue in body["issues"] if issue["rubric_ref"] == "ingest.missing_prescription"
    ]
    assert len(missing) == 1

    reviewed = {
        exercise["exercise_id"]
        for day in updates(result)["submitted_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert "barbell_bench_press" not in reviewed


async def test_a_wholly_unreadable_plan_asks_rather_than_reviews(catalog, scored):
    """If nothing could be identified there is nothing honest to say about it."""
    result = await call(
        score_plan,
        _state(catalog),
        _config(),
        days=_days(("qqq zzz wwww", 3, [8, 10]), ("xyzzy plugh", 3, [8, 10])),
    )

    assert updates(result)["scored"] is False
    assert message(result).status == "error"
    assert "qqq zzz wwww" in message(result).content, "the question must name what was unclear"
    assert scored == [], "a verdict was produced from nothing"


async def test_nothing_at_all_is_an_ask_not_a_crash(catalog, scored):
    """An empty transcription must not become an assessment of an empty plan."""
    result = await call(score_plan, _state(catalog), _config(), days=[])

    assert updates(result)["scored"] is False
    assert message(result).status == "error"
    assert scored == []


async def test_a_low_confidence_lookup_names_the_options(catalog, scored):
    """The model is handed candidates to ask about, never a pick to run with."""
    answer = json.loads(call(lookup_exercise, _state(catalog), raw_text="press"))

    assert answer["exercise_id"] is None
    assert answer["candidates"]
    assert "do not pick one" in answer["note"]


def test_a_confident_lookup_returns_the_match(catalog):
    """The common case still resolves, or the tool would be useless."""
    answer = json.loads(call(lookup_exercise, _state(catalog), raw_text="Barbell Bench Press"))
    assert answer["exercise_id"] == "barbell_bench_press"


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
    assert resolve_exercise("bench press barbell", catalog)["exercise_id"] == "barbell_bench_press"


def test_an_ambiguous_name_returns_candidates_not_a_pick(catalog):
    """Several plausible matches means the user chooses, not the resolver."""
    result = resolve_exercise("press", catalog)
    assert result["exercise_id"] is None
    assert result["candidates"]


def test_leg_press_never_resolves_to_leg_extension(catalog):
    """A recorded failure: scope creep changes what the injury check assesses."""
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
