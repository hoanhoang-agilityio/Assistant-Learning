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
from types import SimpleNamespace

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.core.langgraph.agents.review.state import ReviewState
from app.core.langgraph.agents.review.tools import lookup_exercise, score_plan
from app.core.langgraph.agents.review.transcribe import transcribe
from app.schemas.graph import PastedDay, PastedExercise, PastedPlan
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

    async def fake_score(plan, profile, scope=None):
        seen.append({"plan": plan, "profile": profile, "scope": scope})
        return {"kcal": 2100, "tdee": 2400, "goal": profile.get("goal")}, [], "pass"

    monkeypatch.setattr("app.core.langgraph.agents.review.tools.score", fake_score)
    monkeypatch.setattr("app.core.langgraph.plans.rendering.load_catalog", lambda *a, **k: {})
    return seen


def _state(catalog: dict, **overrides) -> ReviewState:
    """Build a review state the tools can read."""
    return {
        "messages": [],
        "catalog": catalog,
        "profile": dict(PROFILE),
        "submitted": [],
        "submitted_plan": None,
        "unresolved": [],
        "incomplete": [],
        "scored": False,
        **overrides,
    }


def _config() -> dict:
    """A runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _days(*lines: tuple[str, int | None, list[int] | None]) -> list[PastedDay]:
    """Build a transcription from ``(name, sets, reps)`` tuples.

    Validated models rather than dicts, because that is what reaches the tool:
    :func:`app.core.langgraph.agents.review.transcribe.transcribe` produces
    ``PastedDay`` instances and the state carries them as they are.
    """
    return [
        PastedDay(
            day=1,
            name="Pasted day",
            exercises=[
                PastedExercise(
                    raw_name=name,
                    sets=sets,
                    reps_min=(reps or [None])[0],
                    reps_max=(reps or [None])[-1],
                )
                for name, sets, reps in lines
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Read-only, structurally
# ---------------------------------------------------------------------------


async def test_a_review_produces_no_handle_anything_could_be_saved_from(catalog, scored):
    """The absence of a draft_id is what keeps a pasted plan from being adopted."""
    result = await call(
        score_plan, _state(catalog, submitted=_days(("Barbell Bench Press", 4, [6, 8]))), _config()
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
        _state(
            catalog, submitted=_days(("Barbell Bench Press", 8, [6, 8]), ("Back Squat", 8, [5, 8]))
        ),
        _config(),
    )
    body = json.loads(message(result).content)

    assert body["verdict"] in {"pass", "warn", "fail"}
    assert body["macros"], "a review without macros is a review of nothing"
    assert scored, "the verifiers never ran"


async def test_the_review_assesses_what_was_understood(catalog, scored):
    """The scorer sees resolved catalog ids, never the raw text."""
    await call(
        score_plan, _state(catalog, submitted=_days(("db shoulder press", 3, [8, 12]))), _config()
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
        _state(
            catalog,
            submitted=_days(
                ("Zercher good morning off pins", 3, [8, 10]), ("Back Squat", 4, [5, 8])
            ),
        ),
        _config(),
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
        _state(
            catalog, submitted=_days(("Barbell Bench Press", None, None), ("Back Squat", 4, [5, 8]))
        ),
        _config(),
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
        _state(catalog, submitted=_days(("qqq zzz wwww", 3, [8, 10]), ("xyzzy plugh", 3, [8, 10]))),
        _config(),
    )

    assert updates(result)["scored"] is False
    assert message(result).status == "error"
    assert "qqq zzz wwww" in message(result).content, "the question must name what was unclear"
    assert scored == [], "a verdict was produced from nothing"


async def test_nothing_at_all_is_an_ask_not_a_crash(catalog, scored):
    """An empty transcription must not become an assessment of an empty plan."""
    result = await call(score_plan, _state(catalog), _config())

    assert updates(result)["scored"] is False
    assert message(result).status == "error"
    assert scored == []


# ---------------------------------------------------------------------------
# Reading the message is not one of the agent's decisions
# ---------------------------------------------------------------------------


def test_score_plan_takes_no_arguments():
    """The strongest form of the fix, and the reason the rest of it holds.

    Two recorded failures came through this one parameter. It was ``list[dict]``,
    which reaches the model as an array of unconstrained objects — a wrong guess
    at the nesting validated, and every line was then dropped in silence. And it
    made reading the user's message the model's job on a call it could decline.

    Now the plan is transcribed before the agent is invoked and arrives in state,
    so there is no argument left to get wrong. Same move as
    ``test_save_plan_has_no_plan_parameter``: the safest parameter is the absent
    one.
    """
    parameters = set(inspect.signature(score_plan.coroutine or score_plan.func).parameters)
    assert parameters == {"runtime"}

    schema = convert_to_openai_tool(score_plan)["function"]["parameters"]
    assert schema.get("properties", {}) == {}


def test_the_transcription_schema_names_every_field_it_needs():
    """What the model is asked for has to be described where it is asked.

    The prose in a docstring is not a schema. These field names are the contract
    the transcription call is validated against, and ``raw_name`` in particular
    is load-bearing: a field called ``name`` invites the model to write the name
    it thinks was meant, which is the guess the resolver exists to refuse.
    """
    schema = json.dumps(PastedPlan.model_json_schema())

    for field in ("days", "day", "name", "exercises", "raw_name", "sets", "reps_min", "reps_max"):
        assert f'"{field}"' in schema, f"the model is never told about `{field}`"


def test_the_transcription_never_forces_an_invented_prescription():
    """A non-nullable ``sets`` would make the model write a number for a line without one.

    That number is not a formatting detail — it becomes real volume in a real
    assessment, which is what ``ingest.missing_prescription`` exists to report
    instead.
    """
    assert PastedExercise(raw_name="Leg Press").sets is None

    properties = PastedPlan.model_json_schema()["$defs"]["PastedExercise"]["properties"]
    for field in ("sets", "reps_min", "reps_max"):
        assert {"type": "null"} in properties[field]["anyOf"], f"`{field}` cannot be omitted"


async def test_a_line_with_no_name_is_reported_as_a_transcription_fault(catalog, scored):
    """A nameless line must not read as an exercise the user wrote badly."""
    result = await call(
        score_plan,
        _state(catalog, submitted=_days(("", 3, [8, 10]), ("Back Squat", 4, [5, 8]))),
        _config(),
    )

    body = json.loads(message(result).content)
    nameless = [issue for issue in body["issues"] if "no name" in issue["message"]]
    assert len(nameless) == 1
    assert "couldn't confidently identify ''" not in message(result).content


@pytest.mark.parametrize(
    ("low", "high"),
    [(8, 8), (8, None), (None, 8)],
    ids=["fixed count", "only a low end", "only a high end"],
)
async def test_a_half_given_rep_range_still_becomes_a_range(catalog, scored, low, high):
    """ "4x8" is as common as "4x6-8", and every consumer indexes ``reps[1]``.

    A line whose transcription carries one end is worth assessing on that end.
    Dropping it would be the harsher reading of a plan the user did write.
    """
    submitted = [
        PastedDay(
            day=1,
            name="Pasted day",
            exercises=[PastedExercise(raw_name="Back Squat", sets=4, reps_min=low, reps_max=high)],
        )
    ]
    await call(score_plan, _state(catalog, submitted=submitted), _config())

    assert scored[0]["plan"]["days"][0]["exercises"][0]["reps"] == [8, 8]


async def test_a_users_own_day_label_is_not_numbered_twice(catalog, scored):
    """Users write "Day 1 — Upper" themselves; the renderer numbered it again.

    Harmless to the assessment and immediately visible in it: the review opened
    with "Day 1 — Day 1 — Upper". Built plans still need the number, because
    their day names come from the template as "Upper A".
    """
    submitted = [
        PastedDay(
            day=1,
            name="Day 1 — Upper",
            exercises=[PastedExercise(raw_name="Back Squat", sets=4, reps_min=5, reps_max=8)],
        )
    ]
    result = await call(score_plan, _state(catalog, submitted=submitted), _config())
    rendered = json.loads(message(result).content)["plan_rendered"]

    assert "Day 1 — Upper:" in rendered
    assert "Day 1 — Day 1" not in rendered


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


# ---------------------------------------------------------------------------
# Transcription, which happens before the agent exists
# ---------------------------------------------------------------------------


async def test_the_transcription_is_a_validated_call_not_a_parse(monkeypatch):
    """Free text becomes structure through the schema, or it does not become it.

    ``response_format`` is the whole mechanism: a reading the schema rejects
    fails validation instead of arriving half-formed, which is the same reason
    ``IntentDecision`` is never parsed out of a classifier's prose.
    """
    seen: dict = {}

    async def fake_call(messages, model_name=None, response_format=None, **kwargs):
        seen["prompt"] = messages[0].content
        seen["response_format"] = response_format
        return PastedPlan(
            days=[
                PastedDay(
                    day=1,
                    name="Upper",
                    exercises=[
                        PastedExercise(raw_name="Bench Press", sets=4, reps_min=6, reps_max=8)
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "app.core.langgraph.agents.review.transcribe.llm_service",
        SimpleNamespace(call=fake_call),
    )
    days = await transcribe("Day 1 — Upper: Bench Press 4x6-8")

    assert seen["response_format"] is PastedPlan
    assert "Day 1 — Upper: Bench Press 4x6-8" in seen["prompt"]
    assert days[0].exercises[0].raw_name == "Bench Press"


async def test_a_failed_transcription_reads_as_no_plan_not_as_a_crash(monkeypatch):
    """The turn has to end in an answer, and "I couldn't read it" is one."""

    async def fake_call(*args, **kwargs):
        raise RuntimeError("upstream is down")

    monkeypatch.setattr(
        "app.core.langgraph.agents.review.transcribe.llm_service",
        SimpleNamespace(call=fake_call),
    )
    assert await transcribe("Day 1 — Upper: Bench Press 4x6-8") == []


async def test_a_day_with_no_lines_is_not_carried_forward(monkeypatch):
    """A heading the model transcribed but found nothing under is not a day."""

    async def fake_call(*args, **kwargs):
        return PastedPlan(
            days=[
                PastedDay(day=1, name="Upper", exercises=[]),
                PastedDay(
                    day=2,
                    name="Lower",
                    exercises=[
                        PastedExercise(raw_name="Back Squat", sets=4, reps_min=5, reps_max=8)
                    ],
                ),
            ]
        )

    monkeypatch.setattr(
        "app.core.langgraph.agents.review.transcribe.llm_service",
        SimpleNamespace(call=fake_call),
    )
    days = await transcribe("whatever")

    assert [day.name for day in days] == ["Lower"]


# ---------------------------------------------------------------------------
# A generic name against a catalog of qualified variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Bench Press", "barbell_bench_press"),
        ("Lat Pulldown", "lat_pulldown_machine"),
        ("Leg Press", "leg_press_neutral_grip"),
        ("Romanian Deadlift", "romanian_deadlift_tempo"),
    ],
)
def test_the_plainest_names_a_user_can_write_resolve(catalog, written, expected):
    """A recorded failure, and it was the common case rather than an edge one.

    The catalog has no canonical row per movement — no "Bench Press", only four
    qualified variants — so the most ordinary names matched several rows, none
    uniquely, and came back unidentified. Five of the twelve lines in an
    ordinary three-day plan were dropped from the assessment that way.
    """
    assert resolve_exercise(written, catalog)["exercise_id"] == expected


def test_a_style_qualifier_is_discounted_but_a_different_movement_is_not(catalog):
    """ "Leg Press" fits "Leg Press (Neutral Grip)" and "Leg Press Calf Raise".

    Only one of those is a leg press. The grip qualifies how; the calf raise is
    a different movement wearing a longer name, and the review would credit the
    wrong muscle entirely.
    """
    assert resolve_exercise("Leg Press", catalog)["exercise_id"] == "leg_press_neutral_grip"


def test_variants_are_settled_only_when_no_check_could_tell_them_apart(catalog):
    """The proof that makes the pick safe, rather than a preference for one row.

    All four bench press variants credit the same muscles through the same
    joint actions, so the volume and injury checks cannot distinguish them and
    the choice cannot change the review. The ones stood down on come back in
    ``equivalent`` to be named in the answer.
    """
    resolution = resolve_exercise("Bench Press", catalog)
    assert resolution["exercise_id"] == "barbell_bench_press"

    also = {option["exercise_id"] for option in resolution["equivalent"]}
    assert also == {
        "decline_bench_press_neutral_grip",
        "dumbbell_bench_press_machine",
        "incline_bench_press_wide_grip",
    }

    fields = ("movement_pattern", "contribution", "joint_actions", "loaded_positions")
    keys = {
        repr([catalog[i][field] for field in fields]) for i in also | {resolution["exercise_id"]}
    }
    assert len(keys) == 1, "a variant was settled on rows the checks read differently"


@pytest.mark.parametrize("written", ["Squat", "Row", "Curl", "press", "Dip"])
def test_a_genuinely_ambiguous_name_is_still_a_question(catalog, written):
    """Back squat, front squat and goblet squat are not each other.

    The point the variant tiers must not cross: they settle names whose
    candidates the checks read identically, and a bare "Squat" is not one —
    those rows differ in what they load. A one-word query is refused outright,
    however the rows compare.
    """
    resolution = resolve_exercise(written, catalog)

    assert resolution["exercise_id"] is None
    assert resolution["candidates"], "a refusal must name what it might have been"


async def test_an_equivalent_variant_is_reported_not_swapped_in_silence(catalog, scored):
    """The user sees a name in the rendering that is not the one they typed.

    ``info`` rather than ``warn``: the line was assessed, and correctly. What
    the note buys is that "Barbell Bench Press" appearing where they wrote
    "Bench Press" is explained rather than left to look like a misreading.
    """
    submitted = [
        PastedDay(
            day=1,
            name="Upper",
            exercises=[PastedExercise(raw_name="Bench Press", sets=4, reps_min=6, reps_max=8)],
        )
    ]
    result = await call(score_plan, _state(catalog, submitted=submitted), _config())
    body = json.loads(message(result).content)

    assumed = [issue for issue in body["issues"] if issue["rubric_ref"] == "ingest.variant_assumed"]
    assert len(assumed) == 1
    assert assumed[0]["severity"] == "info"
    assert "Barbell Bench Press" in assumed[0]["message"]
    assert "changes nothing" in assumed[0]["message"]

    reviewed = {
        exercise["exercise_id"]
        for day in updates(result)["submitted_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert reviewed == {"barbell_bench_press"}
