"""Tests for changing a plan the user already approved.

``patch_plan`` no longer has a root node of its own: it is the body of the
planning agent's change mode (``docs/supervisor-architecture.md`` §1). It shares
every input and every output with the build path, so ``mode="change"`` is one
parameter rather than a second branch — and the tests follow it there.

Two rules shape the change path, and both are asserted below:

**Modification must not become regeneration.** Rebuilding from scratch would
quietly drop every exercise the user has been happy with for six weeks. What
carries forward is carried, and what a new injury rules out is re-picked.

**A change cannot take a shortcut past the checks.** Adding a session raises
TDEE and breaks a deficit that was correct before, so the change goes through
``commit_draft`` like a build does — the same macros, the same verifiers, the
same handle.
"""

import json
import uuid
from pathlib import Path

import pytest

from app.core.langgraph import drafts
from app.core.langgraph.agents.planning.patch import SUPPORTED_CHANGES, patch_plan
from app.core.langgraph.agents.planning.tools import _change_slots, commit_draft, get_template_slots
from app.core.langgraph.diff import build_diff
from tests.seed import CONTRAINDICATIONS, TEMPLATES
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


@pytest.fixture(scope="module")
def approved_plan(catalog) -> dict:
    """A 4-day plan standing in for one the user already accepted."""
    from app.services.catalog import candidates_for_slot
    from app.services.templates import iter_slots

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


@pytest.fixture(autouse=True)
def _catalog_from_the_seed_file(monkeypatch, catalog):
    """Point every catalog read at the seed file rather than at Postgres."""
    monkeypatch.setattr("app.services.catalog.load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.load_catalog", lambda *a, **k: catalog
    )
    monkeypatch.setattr("app.core.langgraph.rendering.load_catalog", lambda *a, **k: catalog)


@pytest.fixture
def scored(monkeypatch):
    """Score every plan as a pass, without a rubric database behind it."""
    seen: list[dict] = []

    async def fake_score(plan, profile, config=None, scope=None):
        seen.append({"plan": plan, "profile": profile})
        sessions = len(plan.get("days") or [])
        return (
            {"kcal": 1900 + sessions * 50, "tdee": 2200 + sessions * 50, "goal": profile["goal"]},
            [],
            "pass",
        )

    monkeypatch.setattr("app.core.langgraph.agents.planning.tools.score", fake_score)
    monkeypatch.setattr(
        "app.core.langgraph.agents.planning.tools.profile_hash", lambda _profile: "hash"
    )
    monkeypatch.setattr("app.core.langgraph.agents.planning.tools.rubric_version", lambda: "v1")
    return seen


def _state(catalog: dict, plan: dict, **overrides) -> dict:
    """Build a planning state in change mode."""
    return {
        "messages": [],
        "profile": dict(PROFILE),
        "goal": "fat_loss",
        "preferences": "",
        "mode": "change",
        "changes": {"days": 3},
        "base_plan": plan,
        "base_macros": {"kcal": 2100, "tdee": 2400, "goal": "fat_loss"},
        "template": None,
        "slots": [],
        "notes": [],
        "draft_id": None,
        **overrides,
    }


def _config() -> dict:
    """A runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


# ---------------------------------------------------------------------------
# Change mode, through the agent's tools
# ---------------------------------------------------------------------------


async def test_a_change_offers_the_slots_with_what_the_plan_already_uses(catalog, approved_plan):
    """The model is shown the current exercise, so keeping it is the default.

    This is what stops a change reading as a rebuild. Without
    ``current_exercise_id`` the model has nothing marking which option the user
    has been training for six weeks, and a perfectly valid plan replaces all of
    them.
    """
    result = await call(get_template_slots, _state(catalog, approved_plan), _config())
    slots = updates(result)["slots"]

    assert slots
    carried = [slot for slot in slots if "current_exercise_id" in slot]
    assert carried, "no slot carried the exercise the plan already uses"
    for slot in carried:
        assert slot["current_exercise_id"] in catalog


async def test_committing_a_change_with_no_choices_keeps_the_current_exercises(
    catalog, approved_plan, scored
):
    """The normal path: apply the change, keep what it did not touch."""
    drafts.clear()
    prepared = await call(get_template_slots, _state(catalog, approved_plan), _config())
    written = updates(prepared)

    result = await call(
        commit_draft,
        _state(
            catalog,
            approved_plan,
            template=written["template"],
            slots=written["slots"],
            notes=written["notes"],
        ),
        _config(),
        choices=[],
    )
    draft = drafts.read(updates(result)["draft_id"])

    before = {e["exercise_id"] for d in approved_plan["days"] for e in d["exercises"]}
    after = {e["exercise_id"] for d in draft.plan["days"] for e in d["exercises"]}
    assert after & before, "the change discarded every exercise the user had"
    assert len(draft.plan["days"]) == 3, "the change was not applied"


async def test_macros_are_recomputed_for_the_new_day_count(catalog, approved_plan, scored):
    """An extra session raises TDEE, so the old targets cannot be reused."""
    drafts.clear()
    prepared = await call(get_template_slots, _state(catalog, approved_plan), _config())
    written = updates(prepared)

    result = await call(
        commit_draft,
        _state(catalog, approved_plan, template=written["template"], slots=written["slots"]),
        _config(),
        choices=[],
    )
    draft = drafts.read(updates(result)["draft_id"])

    assert draft.macros["tdee"] != 2400, "the change kept the macros of the old day count"
    assert scored, "the change skipped the verifiers"


async def test_a_change_carries_a_diff_and_a_build_does_not(catalog, approved_plan, scored):
    """The diff is what the confirm question shows; a build has nothing to show."""
    drafts.clear()
    prepared = await call(get_template_slots, _state(catalog, approved_plan), _config())
    written = updates(prepared)

    changed = await call(
        commit_draft,
        _state(catalog, approved_plan, template=written["template"], slots=written["slots"]),
        _config(),
        choices=[],
    )
    assert drafts.read(updates(changed)["draft_id"]).diff is not None

    built = await call(
        commit_draft,
        _state(
            catalog,
            approved_plan,
            mode="build",
            base_plan=None,
            template=written["template"],
            slots=written["slots"],
        ),
        _config(),
        choices=[],
    )
    assert drafts.read(updates(built)["draft_id"]).diff is None


async def test_an_unapplicable_change_refuses_rather_than_rebuilding(catalog, approved_plan):
    """A change nobody can apply must not quietly become a fresh plan."""
    result = await call(
        get_template_slots, _state(catalog, approved_plan, changes={"tempo": "slow"}), _config()
    )

    assert updates(result)["template"] is None
    assert message(result).status == "error"
    assert "tempo" in message(result).content


def test_change_slots_reports_a_template_the_library_has_lost(catalog, approved_plan):
    """A plan built from a retired programme cannot be patched, and says so."""
    orphaned = {**approved_plan, "template_id": "no_longer_in_the_library"}
    template, slots, notes = _change_slots(orphaned, {"goal": "recomp"}, PROFILE, catalog)

    assert template is None
    assert slots == []
    assert notes[-1]["rubric_ref"] == "templates.missing"


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


def test_the_supported_changes_are_the_ones_the_tool_advertises():
    """A delta the model can name and the patcher cannot apply is a dead end."""
    assert SUPPORTED_CHANGES == {"days", "goal"}

    from app.core.langgraph.supervisor import tools as supervisor_tools

    doc = supervisor_tools.planning_agent.description
    for change in SUPPORTED_CHANGES:
        assert change in doc, f"{change} is applicable but never mentioned to the model"


# ---------------------------------------------------------------------------
# The diff
# ---------------------------------------------------------------------------


def test_diff_reports_no_change_honestly():
    """An identical plan must not be dressed up as an adjustment."""
    plan = {"days": [{"name": "A", "exercises": [{"name": "Squat"}]}]}
    diff = build_diff(plan, plan, {"kcal": 2000}, {"kcal": 2000})

    assert diff["added"] == []
    assert diff["removed"] == []


def test_the_confirm_question_is_built_from_the_draft_not_the_call(catalog, approved_plan):
    """What the user approves must be what the store holds.

    A question assembled from the model's tool-call arguments would be a question
    about a different plan than the one about to be written.
    """
    drafts.clear()
    from app.core.langgraph.supervisor.agent import _save_description

    draft = drafts.mint(
        plan=approved_plan,
        macros={"kcal": 2100},
        issues=[],
        verdict="pass",
        plan_rendered="Split: Upper / Lower, 4 days",
        profile_hash="hash",
        rubric_version="v1",
        diff={"summary": "Drops you from 4 sessions to 3."},
    )

    question = _save_description({"args": {"draft_id": draft.draft_id}}, {}, None)
    assert "Drops you from 4 sessions to 3." in question
    assert "Split: Upper / Lower, 4 days" in question
    assert "until you say yes" in question


def test_an_expired_draft_does_not_produce_a_confident_question():
    """A gate that cannot read what it is gating must say so."""
    drafts.clear()
    from app.core.langgraph.supervisor.agent import _save_description

    question = _save_description({"args": {"draft_id": "gone"}}, {}, None)
    assert "expired" in question
