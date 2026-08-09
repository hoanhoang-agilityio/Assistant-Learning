"""Tests for the planning agent.

Runs against the real seeded catalog file (not the database) with the LLM node
stubbed, so the assertions are about the pipeline's guarantees rather than about
a model's output:

* the prescription in the plan is the template's, never the model's
* a model choice outside the candidate list cannot enter the plan
* an unfillable slot is dropped with an explanation, not failed
* no matching template is reported at select_template, not at verify
"""

import json
import uuid
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.core.langgraph.agents.planning.graph import build_planning_graph
from app.core.langgraph.agents.planning.nodes import _validate
from app.core.langgraph.agents.planning.state import ExerciseChoice, ExerciseChoices
from app.services.templates import iter_slots
from tests.seed import TEMPLATES

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_seed.json"

pytestmark = pytest.mark.skipif(
    not _CATALOG_FILE.exists(),
    reason="data/exercise_seed.json is missing — the catalog fixture needs it",
)


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict]:
    """The seeded catalog, keyed by id."""
    rows = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture
def stub_llm(monkeypatch):
    """Replace the chooser LLM with a controllable stub.

    Returns a function taking the choices the model should return; call it with
    ``None`` to make the call fail.
    """

    def _install(choices: list[tuple[str, str]] | None):
        async def fake_call(*_args, **_kwargs):
            if choices is None:
                raise RuntimeError("model unavailable")
            return ExerciseChoices(
                choices=[ExerciseChoice(slot_id=s, exercise_id=e) for s, e in choices]
            )

        monkeypatch.setattr("app.core.langgraph.agents.planning.nodes.llm_service.call", fake_call)

    return _install


def _state(catalog: dict, **overrides) -> dict:
    """Build a planning state with a full-gym, uninjured default profile."""
    equipment = sorted({item for row in catalog.values() for item in row["equipment"]})
    return {
        "profile": {
            "days_per_week": 4,
            "level": 2,
            "equipment": equipment,
            "injuries": [],
        },
        "goal": "fat_loss",
        "preferences": "",
        "catalog": catalog,
        "template": None,
        "slots": [],
        "draft_plan": None,
        "issues": [],
        **overrides,
    }


def _config() -> dict:
    """A runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


async def _run(catalog, stub_llm, choices=None, **overrides) -> dict:
    """Run the planning graph once with a stubbed chooser."""
    stub_llm(choices)
    graph = build_planning_graph()
    return await graph.ainvoke(_state(catalog, **overrides), _config())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_builds_a_plan_and_never_drops_a_slot_silently(catalog, stub_llm):
    """Every slot is either filled or explained. Nothing disappears quietly.

    A full slate is not asserted, because it depends on catalog depth: a level-2
    profile gets no hinge, since the only two hinge exercises are barbell
    deadlifts rated skill 4. Refusing to prescribe those to a novice is correct.
    Dropping them *without saying so* would not be.
    """
    result = await _run(catalog, stub_llm)
    plan = result["draft_plan"]

    assert plan is not None
    assert plan["template_id"] == "upper_lower_4day"
    assert len(plan["days"]) == 4

    placed = sum(len(day["exercises"]) for day in plan["days"])
    expected = len(iter_slots(TEMPLATES["upper_lower_4day"]))
    assert len(result["issues"]) == expected - placed, (
        f"{expected - placed} slots were dropped but {len(result['issues'])} issues were raised"
    )


async def test_a_deep_enough_catalog_fills_every_slot(catalog, stub_llm):
    """With no skill ceiling the pipeline fills the whole template.

    Complements the test above: it proves the gaps there come from catalog depth
    and the skill gate, not from a defect in the assembly pipeline.
    """
    advanced = {
        "days_per_week": 4,
        "level": 5,
        "equipment": sorted({i for r in catalog.values() for i in r["equipment"]}),
        "injuries": [],
    }
    result = await _run(catalog, stub_llm, profile=advanced)

    placed = sum(len(day["exercises"]) for day in result["draft_plan"]["days"])
    assert placed == len(iter_slots(TEMPLATES["upper_lower_4day"]))
    assert result["issues"] == []


async def test_prescription_comes_from_the_template(catalog, stub_llm):
    """workflow.md 1.1: sets, reps and RIR are the template's, not the model's."""
    result = await _run(catalog, stub_llm)
    slots = {slot["slot_id"]: slot for slot in iter_slots(TEMPLATES["upper_lower_4day"])}

    for day in result["draft_plan"]["days"]:
        for exercise in day["exercises"]:
            slot = slots[exercise["slot_id"]]
            assert exercise["sets"] == slot["sets"]
            assert exercise["reps"] == slot["reps"]
            assert exercise["rir"] == slot["rir"]


async def test_every_chosen_exercise_exists_in_the_catalog(catalog, stub_llm):
    """assemble_plan validates ids; this asserts the happy path satisfies it."""
    result = await _run(catalog, stub_llm)
    for day in result["draft_plan"]["days"]:
        for exercise in day["exercises"]:
            assert exercise["exercise_id"] in catalog


# ---------------------------------------------------------------------------
# The model cannot escape the candidate list
# ---------------------------------------------------------------------------


async def test_a_choice_outside_the_candidate_list_is_rejected(catalog, stub_llm):
    """workflow.md 6.3: the model picks from a filtered list, it cannot extend it."""
    result = await _run(
        catalog, stub_llm, choices=[("ua_horiz_push", "definitely_not_a_real_exercise")]
    )

    chosen = {
        exercise["slot_id"]: exercise["exercise_id"]
        for day in result["draft_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert chosen["ua_horiz_push"] != "definitely_not_a_real_exercise"
    assert chosen["ua_horiz_push"] in catalog


async def test_a_contraindicated_choice_cannot_be_smuggled_in(catalog, stub_llm):
    """Naming a filtered-out exercise must not put it back in the plan."""
    injured = {
        "days_per_week": 4,
        "level": 2,
        "equipment": sorted({i for r in catalog.values() for i in r["equipment"]}),
        "injuries": ["knee_pain_patellofemoral"],
    }
    result = await _run(catalog, stub_llm, choices=[("la_squat", "back_squat")], profile=injured)

    chosen = {
        exercise["slot_id"]: exercise["exercise_id"]
        for day in result["draft_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert chosen.get("la_squat") != "back_squat", "a contraindicated exercise entered the plan"


async def test_an_llm_failure_still_produces_a_plan(catalog, stub_llm):
    """Every slot has a valid default, so a failed call costs variety, not the plan."""
    result = await _run(catalog, stub_llm, choices=None)
    assert result["draft_plan"] is not None
    assert len(result["draft_plan"]["days"]) == 4


async def test_the_model_choice_is_honoured_when_valid(catalog, stub_llm):
    """The guardrails must not make the model's contribution meaningless."""
    baseline = await _run(catalog, stub_llm)

    slot = next(s for s in baseline["slots"] if s["slot_id"] == "ua_horiz_push")
    # Pick from the slot's own candidate list, which is the only set the node
    # accepts — anything else exercises the rejection path instead.
    alternative = next(
        candidate["exercise_id"]
        for candidate in slot["candidates"]
        if candidate["exercise_id"] != slot["exercise_id"]
    )

    result = await _run(catalog, stub_llm, choices=[("ua_horiz_push", alternative)])
    chosen = {
        exercise["slot_id"]: exercise["exercise_id"]
        for day in result["draft_plan"]["days"]
        for exercise in day["exercises"]
    }
    assert chosen["ua_horiz_push"] == alternative


# ---------------------------------------------------------------------------
# Degraded paths
# ---------------------------------------------------------------------------


async def test_an_unfillable_slot_is_dropped_with_an_explanation(catalog, stub_llm):
    """Shoulder impingement rules out every vertical press — omit it and say why."""
    injured = {
        "days_per_week": 4,
        "level": 2,
        "equipment": sorted({i for r in catalog.values() for i in r["equipment"]}),
        "injuries": ["shoulder_impingement"],
    }
    result = await _run(catalog, stub_llm, profile=injured)

    assert result["draft_plan"] is not None, "an unfillable slot must not fail the build"

    slot_ids = {
        exercise["slot_id"] for day in result["draft_plan"]["days"] for exercise in day["exercises"]
    }
    assert "ua_vert_push" not in slot_ids

    dropped = [i for i in result["issues"] if "vertical push" in i["location"]]
    assert len(dropped) == 1
    assert dropped[0]["severity"] == "warn"
    assert dropped[0]["source"] == "injury"


async def test_no_matching_template_is_reported_early(catalog, stub_llm):
    """workflow.md 12: a conflicting constraint is caught here, not at verify."""
    impossible = {
        "days_per_week": 6,
        "level": 2,
        "equipment": ["resistance_band"],
        "injuries": [],
    }
    result = await _run(catalog, stub_llm, profile=impossible)

    assert result["draft_plan"] is None
    assert [i["severity"] for i in result["issues"]] == ["block"]
    assert result["issues"][0]["rubric_ref"] == "templates.no_match"


async def test_equipment_only_profile_degrades_rather_than_crashing(catalog, stub_llm):
    """A sparse home gym drops slots but must still produce something usable."""
    home = {
        "days_per_week": 4,
        "level": 2,
        "equipment": ["dumbbell", "bodyweight"],
        "injuries": [],
    }
    result = await _run(catalog, stub_llm, profile=home)

    if result["draft_plan"] is not None:
        assert result["draft_plan"]["days"], "a plan with zero days is not a plan"
    assert any(i["severity"] == "warn" for i in result["issues"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_rejects_a_modified_prescription(catalog):
    """workflow.md 6.4: an altered set count is a bug, and must raise."""
    template = TEMPLATES["upper_lower_4day"]
    slot = iter_slots(template)[0]
    exercise_id = next(
        row["exercise_id"] for row in catalog.values() if row["movement_pattern"] == slot["pattern"]
    )
    plan = {
        "template_id": template["template_id"],
        "days": [
            {
                "name": slot["day_name"],
                "exercises": [
                    {
                        "slot_id": slot["slot_id"],
                        "exercise_id": exercise_id,
                        "sets": slot["sets"] + 3,
                        "reps": slot["reps"],
                        "rir": slot["rir"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="prescription was modified"):
        _validate(plan, template, catalog)


def test_validate_rejects_an_unknown_exercise(catalog):
    """A plan referencing an exercise the catalog lost is unreadable downstream."""
    template = TEMPLATES["upper_lower_4day"]
    slot = iter_slots(template)[0]
    plan = {
        "template_id": template["template_id"],
        "days": [
            {
                "name": slot["day_name"],
                "exercises": [
                    {
                        "slot_id": slot["slot_id"],
                        "exercise_id": "removed_from_catalog",
                        "sets": slot["sets"],
                        "reps": slot["reps"],
                        "rir": slot["rir"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="unknown exercise"):
        _validate(plan, template, catalog)


# ---------------------------------------------------------------------------
# Subgraph shape
# ---------------------------------------------------------------------------


def test_planning_state_has_no_messages():
    """The planner receives extracted preferences, never the raw transcript."""
    from app.core.langgraph.agents.planning.state import PlanningState

    assert "messages" not in PlanningState.__annotations__


def test_subgraph_compiles_standalone_and_under_a_checkpointer(catalog):
    """The agent must build with and without persistence."""
    graph = build_planning_graph()
    assert graph.name == "planning"
    assert {
        "select_template",
        "filter_candidates",
        "choose_exercises",
        "assemble_plan",
    } <= set(graph.get_graph().nodes)

    from langgraph.graph import StateGraph

    from app.core.langgraph.agents.planning.nodes import select_template
    from app.core.langgraph.agents.planning.state import PlanningState

    builder = StateGraph(PlanningState)
    builder.add_node("select_template", select_template)
    builder.set_entry_point("select_template")
    assert builder.compile(checkpointer=MemorySaver(), name="planning-test") is not None
