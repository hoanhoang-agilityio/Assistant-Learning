"""Tests for the planning agent.

Runs against the real seeded catalog file (not the database), calling the tool
bodies directly. That is where the guarantees moved: choosing an exercise is now
the agent's own loop rather than one structured call, so what has to hold is that
the tools it loops over cannot be talked out of anything.

* the prescription in the plan is the template's, never the model's
* a choice outside the candidate list cannot enter the plan
* a contraindicated exercise cannot be smuggled back in by naming it
* an unfillable slot is dropped with an explanation, not failed
* no matching template is reported when the slots are asked for, not at verify
* only ``commit_draft`` mints a handle, and every handle carries macros
"""

import json
import uuid
from pathlib import Path

import pytest

from app.core.langgraph.agents.planning.state import PlanningState
from app.core.langgraph.agents.planning.tools import (
    _apply_choices,
    _assemble,
    _build_slots,
    _split_preference_notes,
    _validate,
    commit_draft,
    get_exercise_candidates,
    get_template_slots,
)
from app.core.langgraph.plans.rendering import render_prescription
from app.core.langgraph.runtime import draft_store as drafts
from app.services.templates import iter_slots
from tests.seed import TEMPLATES
from tests.support import call, message, updates

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


@pytest.fixture(autouse=True)
def _catalog_from_the_seed_file(monkeypatch, catalog):
    """Point every catalog read at the seed file rather than at Postgres."""
    monkeypatch.setattr("app.services.catalog.load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.commit.load_catalog", lambda *a, **k: catalog
    )
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.slots.load_catalog", lambda *a, **k: catalog
    )
    monkeypatch.setattr("app.core.langgraph.plans.rendering.load_catalog", lambda *a, **k: catalog)


def _profile(catalog: dict, **overrides) -> dict:
    """A full-gym, uninjured profile the macro calculation can also run on."""
    equipment = sorted({item for row in catalog.values() for item in row["equipment"]})
    return {
        "weight_kg": 75.0,
        "height_cm": 175.0,
        "age": 28,
        "sex": "male",
        "activity_level": "light",
        "days_per_week": 4,
        "level": 2,
        "goal": "fat_loss",
        "equipment": equipment,
        "injuries": [],
        **overrides,
    }


def _state(catalog: dict, **overrides) -> PlanningState:
    """Build a planning state the tools can read."""
    return {
        "messages": [],
        "profile": _profile(catalog),
        "goal": "fat_loss",
        "preferences": "",
        "mode": "build",
        "changes": {},
        "base_plan": None,
        "base_macros": None,
        "template": None,
        "slots": [],
        "notes": [],
        "draft_id": None,
        **overrides,
    }


def _config() -> dict:
    """A runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


async def _slots(catalog, **overrides) -> tuple[dict, list[dict], list[dict]]:
    """Ask for the slots and return ``(template, slots, notes)`` from state."""
    result = await call(get_template_slots, _state(catalog, **overrides), _config())
    written = updates(result)
    return written["template"], written["slots"], written["notes"]


def _placed(plan: dict) -> dict[str, str]:
    """Index a plan's chosen exercises by the slot they fill."""
    return {
        exercise["slot_id"]: exercise["exercise_id"]
        for day in plan["days"]
        for exercise in day["exercises"]
    }


# ---------------------------------------------------------------------------
# Getting the slots
# ---------------------------------------------------------------------------


async def test_slots_carry_their_own_candidate_lists(catalog):
    """A slot list without candidates is useless, so the two arrive together."""
    template, slots, _notes = await _slots(catalog)

    assert template["template_id"] == "upper_lower_4day"
    assert slots
    for slot in slots:
        assert slot["candidates"], f"{slot['slot_id']} was offered with nothing to choose from"
        for candidate in slot["candidates"]:
            assert candidate["exercise_id"] in catalog


async def test_no_slot_disappears_without_an_explanation(catalog):
    """Every template slot is either offered or accounted for in the notes."""
    _template, slots, notes = await _slots(catalog)

    expected = len(iter_slots(TEMPLATES["upper_lower_4day"]))
    assert len(slots) + len(notes) == expected, (
        f"{expected - len(slots)} slots were dropped but {len(notes)} notes were raised"
    )


async def test_a_deep_enough_catalog_offers_every_slot(catalog):
    """With no skill ceiling every slot is fillable — the gaps are catalog depth."""
    _template, slots, notes = await _slots(catalog, profile=_profile(catalog, level=5))

    assert len(slots) == len(iter_slots(TEMPLATES["upper_lower_4day"]))
    assert notes == []


async def test_no_matching_template_is_reported_when_slots_are_asked_for(catalog):
    """A conflicting constraint is caught here, not at verify."""
    impossible = _profile(catalog, days_per_week=6, equipment=["resistance_band"])
    result = await call(get_template_slots, _state(catalog, profile=impossible), _config())

    assert updates(result)["template"] is None
    assert message(result).status == "error"
    notes = updates(result)["notes"]
    assert [note["severity"] for note in notes] == ["block"]
    assert notes[0]["rubric_ref"] == "templates.no_match"


async def test_an_unfillable_slot_is_dropped_with_an_explanation(catalog):
    """Shoulder impingement rules out every vertical press — omit it and say why."""
    injured = _profile(catalog, injuries=["shoulder_impingement"])
    template, slots, notes = await _slots(catalog, profile=injured)

    assert template is not None, "an unfillable slot must not fail the build"
    assert "ua_vert_push" not in {slot["slot_id"] for slot in slots}

    dropped = [note for note in notes if "vertical push" in note["location"]]
    assert len(dropped) == 1
    assert dropped[0]["severity"] == "warn"
    assert dropped[0]["source"] == "injury"


async def test_candidates_can_be_narrowed_but_never_widened(catalog):
    """Excluding an id removes it; nothing the caller passes can add one."""
    _template, slots, _notes = await _slots(catalog)
    slot = slots[0]
    first = slot["candidates"][0]["exercise_id"]

    listed = json.loads(
        call(get_exercise_candidates, _state(catalog, slots=slots), slot_id=slot["slot_id"])
    )
    assert {candidate["exercise_id"] for candidate in listed["candidates"]} == {
        candidate["exercise_id"] for candidate in slot["candidates"]
    }

    narrowed = json.loads(
        call(
            get_exercise_candidates,
            _state(catalog, slots=slots),
            slot_id=slot["slot_id"],
            exclude_ids=[first],
        )
    )
    assert first not in {candidate["exercise_id"] for candidate in narrowed["candidates"]}


def test_an_unknown_slot_is_named_rather_than_guessed(catalog):
    """Asking for a slot that does not exist gets a correction, not a list."""
    answer = call(get_exercise_candidates, _state(catalog), slot_id="no_such_slot")
    assert "no_such_slot" in answer
    assert "get_template_slots" in answer


# ---------------------------------------------------------------------------
# The model cannot escape the candidate list
# ---------------------------------------------------------------------------


async def test_a_choice_outside_the_candidate_list_is_rejected(catalog):
    """The model picks from a filtered list; it cannot extend it."""
    _template, slots, _notes = await _slots(catalog)
    filled, rejected = _apply_choices(
        slots, [{"slot_id": "ua_horiz_push", "exercise_id": "definitely_not_a_real_exercise"}]
    )

    assert rejected == 1
    chosen = {slot["slot_id"]: slot["exercise_id"] for slot in filled}
    assert chosen["ua_horiz_push"] != "definitely_not_a_real_exercise"
    assert chosen["ua_horiz_push"] in catalog


async def test_a_contraindicated_choice_cannot_be_smuggled_in(catalog):
    """Naming a filtered-out exercise must not put it back in the plan."""
    injured = _profile(catalog, injuries=["knee_pain_patellofemoral"])
    _template, slots, _notes = await _slots(catalog, profile=injured)

    filled, _rejected = _apply_choices(
        slots, [{"slot_id": "la_squat", "exercise_id": "back_squat"}]
    )
    chosen = {slot["slot_id"]: slot["exercise_id"] for slot in filled}
    assert chosen.get("la_squat") != "back_squat", "a contraindicated exercise entered the plan"


async def test_a_valid_choice_is_honoured(catalog):
    """The guardrails must not make the model's contribution meaningless."""
    _template, slots, _notes = await _slots(catalog)
    slot = next(entry for entry in slots if entry["slot_id"] == "ua_horiz_push")
    alternative = slot["candidates"][-1]["exercise_id"]

    filled, rejected = _apply_choices(
        slots, [{"slot_id": "ua_horiz_push", "exercise_id": alternative}]
    )
    chosen = {entry["slot_id"]: entry["exercise_id"] for entry in filled}
    assert chosen["ua_horiz_push"] == alternative
    assert rejected == 0


async def test_no_choices_at_all_still_produces_a_full_plan(catalog):
    """Every slot has a valid default, so silence costs variety, not the plan."""
    template, slots, _notes = await _slots(catalog)
    filled, rejected = _apply_choices(slots, [])
    plan = _assemble(template, filled, catalog)

    assert rejected == 0
    assert len(plan["days"]) == 4
    assert all(exercise_id in catalog for exercise_id in _placed(plan).values())


async def test_a_change_keeps_what_it_was_not_asked_to_change(catalog):
    """A named slot's current exercise survives a commit with no choices."""
    _template, slots, _notes = await _slots(catalog)
    marked = [
        {**slot, "current_exercise_id": slot["candidates"][-1]["exercise_id"]} for slot in slots
    ]

    filled, _rejected = _apply_choices(marked, [])
    for slot in filled:
        assert slot["exercise_id"] == slot["current_exercise_id"]


# ---------------------------------------------------------------------------
# Assembly and validation
# ---------------------------------------------------------------------------


async def test_prescription_comes_from_the_template(catalog):
    """Sets, reps and RIR are the template's, not the model's."""
    template, slots, _notes = await _slots(catalog)
    filled, _rejected = _apply_choices(slots, [])
    plan = _assemble(template, filled, catalog)

    by_id = {slot["slot_id"]: slot for slot in iter_slots(TEMPLATES["upper_lower_4day"])}
    for day in plan["days"]:
        for exercise in day["exercises"]:
            slot = by_id[exercise["slot_id"]]
            assert exercise["sets"] == slot["sets"]
            assert exercise["reps"] == slot["reps"]
            assert exercise["rir"] == slot["rir"]


def test_validate_rejects_a_modified_prescription(catalog):
    """An altered set count is a bug, and must raise."""
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
# Committing a draft
# ---------------------------------------------------------------------------


@pytest.fixture
def scored(monkeypatch):
    """Score every plan as a pass, without a rubric database behind it.

    What ``commit_draft`` has to guarantee is that scoring happened and that its
    output reached the draft. Which findings the real rubrics produce is
    ``test_app_verification.py``'s subject, not this module's.
    """
    seen: list[dict] = []

    async def fake_score(plan, profile, scope=None):
        seen.append({"plan": plan, "profile": profile})
        return (
            {"kcal": 2100, "tdee": 2400, "goal": profile.get("goal"), "protein_g": 150},
            [],
            "pass",
        )

    monkeypatch.setattr("app.core.langgraph.agents.planning.tools.commit.score", fake_score)
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.commit.profile_hash", lambda _profile: "hash"
    )
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.commit.rubric_version", lambda: "v1"
    )
    return seen


async def test_commit_draft_mints_a_handle_carrying_macros(catalog, scored):
    """Every envelope with a draft_id carries non-None macros. §11.1."""
    drafts.clear()
    template, slots, _notes = await _slots(catalog)

    result = await call(
        commit_draft, _state(catalog, template=template, slots=slots), _config(), choices=[]
    )
    draft_id = updates(result)["draft_id"]
    draft = drafts.read(draft_id)

    assert draft is not None
    assert draft.macros, "a draft without macros is the bug the bundling prevents"
    assert draft.verdict == "pass"
    assert scored, "commit_draft returned a draft without scoring the plan"


async def test_committing_without_slots_is_an_error_not_an_empty_plan(catalog, scored):
    """Assembling nothing must not mint a handle to nothing."""
    result = await call(commit_draft, _state(catalog), _config(), choices=[])

    assert "draft_id" not in updates(result)
    assert message(result).status == "error"


async def test_setup_notes_travel_into_the_draft(catalog, scored):
    """A dropped slot is still reported once the plan is committed."""
    drafts.clear()
    injured = _profile(catalog, injuries=["shoulder_impingement"])
    template, slots, notes = await _slots(catalog, profile=injured)
    assert notes, "this fixture is meant to drop a slot"

    result = await call(
        commit_draft,
        _state(catalog, profile=injured, template=template, slots=slots, notes=notes),
        _config(),
        choices=[],
    )
    draft = drafts.read(updates(result)["draft_id"])
    assert any(issue["rubric_ref"].startswith("contraindications.") for issue in draft.issues)


async def test_the_plan_leaves_as_text_not_as_json(catalog, scored):
    """The model describes the plan; it does not get structure to copy."""
    drafts.clear()
    template, slots, _notes = await _slots(catalog)

    result = await call(
        commit_draft, _state(catalog, template=template, slots=slots), _config(), choices=[]
    )
    body = json.loads(message(result).content)

    assert "plan_rendered" in body
    assert "days" not in body, "the raw plan reached the model's context"
    assert "Sessions a week: 4" in body["plan_rendered"]


# ---------------------------------------------------------------------------
# Agent shape
# ---------------------------------------------------------------------------


def test_the_agent_has_no_field_to_write_a_plan_into():
    """Its only output is a handle: there is nowhere to put a plan of its own."""
    annotations = PlanningState.__annotations__
    assert "plan" not in annotations
    assert "draft_plan" not in annotations
    assert "draft_id" in annotations


def test_only_commit_draft_mints_a_handle():
    """The other two tools have no path to the draft store."""
    import inspect

    from app.core.langgraph.agents.planning import tools as planning_tools

    minting = [
        name
        for name, obj in vars(planning_tools).items()
        if callable(getattr(obj, "func", None)) or callable(getattr(obj, "coroutine", None))
        for source in [inspect.getsource(obj.coroutine or obj.func)]
        if "drafts.mint" in source
    ]
    assert minting == ["commit_draft"]


# ---------------------------------------------------------------------------
# Rendering the prescription
# ---------------------------------------------------------------------------


def test_a_held_movement_renders_in_seconds_not_reps():
    """The plank is held, and the slot's rep range must not be read as one.

    ``anti_extension`` slots carry ``reps: [12, 20]``. Rendering that for the
    plank produced "3 sets x 12-20 reps" — and simply relabelling the same two
    numbers as seconds would prescribe a 12-second plank, so the duration is a
    separate range on the catalog entry.
    """
    catalog = {
        "plank": {"unit": "seconds", "duration_seconds": [30, 60]},
        "ab_wheel": {"unit": "reps", "duration_seconds": None},
    }
    slot = {"sets": 3, "reps": [12, 20], "rir": [1, 2]}

    held = render_prescription({**slot, "exercise_id": "plank"}, catalog)
    assert held == "3 sets x 30-60 seconds, RIR 1-2"
    assert "reps" not in held

    # Same slot, same rep range, counted movement — must be untouched.
    counted = render_prescription({**slot, "exercise_id": "ab_wheel"}, catalog)
    assert counted == "3 sets x 12-20 reps, RIR 1-2"


def test_prescription_falls_back_to_reps_for_an_unknown_exercise():
    """A plan naming a retired exercise still renders rather than raising."""
    exercise = {"exercise_id": "retired_movement", "sets": 4, "reps": [6, 8], "rir": [1, 2]}
    assert render_prescription(exercise, {}) == "4 sets x 6-8 reps, RIR 1-2"

    # A pasted plan resolved to no catalog id at all.
    assert (
        render_prescription({**exercise, "exercise_id": None}, {}) == "4 sets x 6-8 reps, RIR 1-2"
    )


# ---------------------------------------------------------------------------
# Honouring — or admitting — a requested split
# ---------------------------------------------------------------------------


def test_a_requested_split_that_cannot_be_honoured_is_reported():
    """Silence here delivered a plan that was not the shape asked for.

    ``preferences`` reaches the model's choice of exercise but never template
    selection, and the library holds exactly one 4-day programme. "an upper body
    focused 4 day plan" therefore produced the balanced Upper/Lower split with
    nothing said about it — a reasonable plan, presented as though it were the
    request.
    """
    template = {
        "name": "Upper / Lower, 4 days",
        "days": [{"name": n} for n in ("Upper A", "Lower A", "Upper B", "Lower B")],
    }

    issues = _split_preference_notes("upper-body focused", template, 1)
    assert len(issues) == 1
    note = issues[0]
    assert note["severity"] == "info", "a library limit is not a rubric violation"
    assert note["rubric_ref"] == "templates.split_preference_unmatched"
    assert "Upper A / Lower A / Upper B / Lower B" in note["message"], (
        "the answer must name the split the user is actually getting"
    )


def test_an_exercise_preference_is_not_mistaken_for_a_split_request():
    """ "Hates burpees" is a choice for the model, and it handles it.

    Reporting a library limit there would be noise on every plan, and noise in
    the findings is how the real findings stop being read.
    """
    template = {"name": "Upper / Lower, 4 days", "days": [{"name": "Upper A"}]}
    for preference in ("hates burpees", "prefers dumbbells over machines", ""):
        assert _split_preference_notes(preference, template, 1) == [], preference


def test_build_slots_never_returns_a_template_with_nothing_to_fill(catalog):
    """A template every slot of which was dropped is not a plan to offer."""
    nothing_available = _profile(catalog, equipment=[])
    template, slots, notes = _build_slots(nothing_available, "fat_loss", "", catalog)

    assert template is None
    assert slots == []
    assert notes, "dropping every slot must be explained"
