"""Data-integrity tests for the exercise catalog.

These exist because the catalog's safety metadata fails *silently* when it is
wrong. The raw seed shipped ``joint_actions: ["compound"]`` on every row — a
value the contraindication rubric never names — so the set intersection the
injury check performs was always empty. Nothing raised. No test failed. Every
plan simply passed the injury screen without being screened.

A unit test of ``check_injury`` cannot catch that, because it uses a fixture
catalog with correct attributes. Only a test that asserts against the *real*
catalog can. That is what this file is.

Each test states the failure it prevents, not just the invariant it checks.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from app.core.langgraph.agents.verification.checks import check_volume
from app.core.langgraph.rubrics import CONTRAINDICATIONS, VOLUME_LANDMARKS
from app.core.langgraph.templates import TEMPLATES, iter_slots
from app.services.catalog import (
    candidates_for_slot,
    filter_candidates,
    forbidden_joint_actions,
    forbidden_loaded_positions,
)
from app.services.movement_taxonomy import MOVEMENT_ATTRIBUTES

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "exercise_seed.json"

pytestmark = pytest.mark.skipif(
    not _CATALOG_FILE.exists(),
    reason="data/exercise_seed.json is missing — the catalog fixture needs it",
)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    """The normalized catalog as a list of rows."""
    return json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog(rows) -> dict[str, dict]:
    """The catalog keyed by id, shaped as the checks and filters consume it."""
    return {row["id"]: {**row, "exercise_id": row["id"]} for row in rows}


@pytest.fixture(scope="module")
def full_gym(rows) -> dict:
    """A profile owning every piece of equipment the catalog references."""
    return {
        "equipment": sorted({item for row in rows for item in row["equipment"]}),
        "level": 5,
        "injuries": [],
    }


# ---------------------------------------------------------------------------
# Structural integrity
# ---------------------------------------------------------------------------


def test_ids_are_unique(rows):
    """`id` is the table's primary key — a duplicate fails the seed insert."""
    duplicates = [k for k, v in Counter(r["id"] for r in rows).items() if v > 1]
    assert duplicates == []


def test_no_leftover_duplicate_suffixes(rows):
    """The raw seed carried `_v2` copies of every row; none may survive."""
    assert [r["id"] for r in rows if r["id"].endswith("_v2")] == []


def test_every_pattern_has_a_taxonomy_entry(rows):
    """An unmapped pattern gets no joint actions and is invisible to injury rules."""
    unmapped = sorted({r["movement_pattern"] for r in rows} - set(MOVEMENT_ATTRIBUTES))
    assert unmapped == []


def test_contribution_is_never_empty(rows):
    """An exercise crediting no muscle contributes nothing to any volume total."""
    empty = [r["id"] for r in rows if not r["contribution"]]
    assert empty == []


def test_contribution_shares_are_plausible(rows):
    """A share outside (0, 1] is a data-entry error, and inflates weekly volume."""
    bad = [
        (r["id"], muscle, share)
        for r in rows
        for muscle, share in r["contribution"].items()
        if not 0 < share <= 1.0
    ]
    assert bad == []


# ---------------------------------------------------------------------------
# The metadata the safety checks match on
# ---------------------------------------------------------------------------


def test_joint_actions_are_not_constant(rows):
    """THE regression guard.

    The raw seed had one value across all 200 rows. A catalog whose joint
    actions never vary cannot distinguish a squat from a curl, so no
    contraindication can ever match.
    """
    distinct = {action for r in rows for action in r["joint_actions"]}
    assert len(distinct) > 1, f"joint_actions collapsed to {distinct}"


def test_loaded_positions_are_not_constant(rows):
    """Same failure as above, for the second attribute the rubric matches on."""
    distinct = {position for r in rows for position in r["loaded_positions"]}
    assert len(distinct) > 1, f"loaded_positions collapsed to {distinct}"


@pytest.mark.parametrize("injury", sorted(CONTRAINDICATIONS["injuries"]))
def test_every_contraindication_matches_at_least_one_exercise(rows, injury):
    """A rule matching nothing is decorative.

    If the rubric forbids `knee_flexion_deep` and no catalog exercise declares
    it, the rule is inert — and inert reads exactly like "this plan is safe".
    """
    entry = CONTRAINDICATIONS["injuries"][injury]
    actions = set(entry["avoid_joint_actions"])
    positions = set(entry.get("avoid_loaded_positions", []))

    matched = [
        r["id"]
        for r in rows
        if set(r["joint_actions"]) & actions or set(r["loaded_positions"]) & positions
    ]
    assert matched, f"'{injury}' matches no exercise in the catalog"


def test_injury_filter_actually_removes_candidates(catalog, full_gym):
    """End to end: a knee injury must shrink the squat candidate list."""
    healthy = filter_candidates({"pattern": "squat"}, full_gym, catalog, set(), set(), limit=99)

    injured_profile = {**full_gym, "injuries": ["knee_pain_patellofemoral"]}
    injured = filter_candidates(
        {"pattern": "squat"},
        injured_profile,
        catalog,
        forbidden_joint_actions(injured_profile, CONTRAINDICATIONS),
        forbidden_loaded_positions(injured_profile, CONTRAINDICATIONS),
        limit=99,
    )

    assert len(injured) < len(healthy), "the knee rule removed nothing from a squat slot"


# ---------------------------------------------------------------------------
# Coverage: can the catalog actually build a plan?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_template_slot_has_a_candidate(catalog, full_gym, template_id):
    """A slot with no candidate cannot be filled and fails assemble_plan."""
    empty = [
        slot["slot_id"]
        for slot in iter_slots(TEMPLATES[template_id])
        if not filter_candidates(slot, full_gym, catalog, set(), set())
    ]
    assert empty == [], f"{template_id} has unfillable slots: {empty}"


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_a_novice_gets_a_real_choice_for_every_slot(catalog, template_id):
    """`choose_exercises` needs at least two options, or it decides nothing.

    A single candidate is not a choice: the model's whole contribution is
    picking between legal options (§6.3), and with one option the LLM call is
    pure cost. A level-2 profile is the demanding case, because the skill gate
    excludes the barbell lifts a beginner should not be handed.
    """
    novice = {
        "equipment": sorted({item for row in catalog.values() for item in row["equipment"]}),
        "level": 2,
        "injuries": [],
    }
    thin = {
        slot["pattern"]: len(filter_candidates(slot, novice, catalog, set(), set(), limit=99))
        for slot in iter_slots(TEMPLATES[template_id])
    }
    assert not [p for p, n in thin.items() if n < 2], (
        f"{template_id}: patterns with fewer than 2 candidates at level 2: "
        f"{ {p: n for p, n in thin.items() if n < 2} }"
    )


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_template_can_be_filled_end_to_end(catalog, full_gym, template_id):
    """Walking a whole template must never strand a slot.

    `candidates_for_slot` drops the no-repeat preference when a pattern has no
    unused exercise left, which the thin patterns in this catalog require: the
    4-day template uses `knee_extension` twice and the catalog has one such
    exercise. A hard exclusion would make that template unbuildable.
    """
    used: set[str] = set()
    stranded: list[str] = []

    for slot in iter_slots(TEMPLATES[template_id]):
        candidates = candidates_for_slot(slot, full_gym, catalog, set(), set(), used_ids=used)
        if not candidates:
            stranded.append(slot["slot_id"])
            continue
        used.add(candidates[0]["exercise_id"])

    assert stranded == [], f"{template_id} has unfillable slots: {stranded}"


@pytest.mark.parametrize("injury", sorted(CONTRAINDICATIONS["injuries"]))
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_injuries_only_strand_genuinely_contraindicated_patterns(
    catalog, full_gym, template_id, injury
):
    """An empty slot is acceptable only when the movement itself is contraindicated.

    Two very different situations produce the same symptom, and telling them
    apart is the whole point of this test:

    * **Correct.** Shoulder impingement bans overhead abduction, and every
      vertical press involves it. The slot has no safe filler, and the plan
      should omit it and say why. Narrowing to nothing is the right answer.

    * **A bug.** Patellofemoral pain banned every squat-pattern exercise
      including the leg press, purely because the pattern-level attributes were
      too coarse. The user who most needs the safety rule got no plan at all.

    So the assertion is not "nothing is stranded" but "everything stranded is
    stranded for a reason the rubric states": every exercise sharing that
    pattern must carry a banned attribute. When this fails, the fix is a
    per-exercise override (`PRESERVE_ATTRIBUTES` in
    scripts/normalize_exercise_seed.py), not a weaker rubric.
    """
    profile = {**full_gym, "injuries": [injury]}
    actions = forbidden_joint_actions(profile, CONTRAINDICATIONS)
    positions = forbidden_loaded_positions(profile, CONTRAINDICATIONS)

    used: set[str] = set()
    over_excluded: list[str] = []

    for slot in iter_slots(TEMPLATES[template_id]):
        candidates = candidates_for_slot(slot, profile, catalog, actions, positions, used_ids=used)
        if candidates:
            used.add(candidates[0]["exercise_id"])
            continue

        # Nothing filled the slot. Was every exercise of this pattern genuinely
        # contraindicated, or did the filter over-reach?
        same_pattern = [
            row for row in catalog.values() if row["movement_pattern"] == slot["pattern"]
        ]
        safe = [
            row["exercise_id"]
            for row in same_pattern
            if not set(row["joint_actions"]) & actions
            and not set(row["loaded_positions"]) & positions
        ]
        if safe:
            over_excluded.append(f"{slot['slot_id']}({slot['pattern']}) despite {safe}")

    assert over_excluded == [], (
        f"'{injury}' over-excluded slots in {template_id}: {over_excluded}. "
        "Safe exercises for that pattern exist but were filtered out."
    )


def test_a_capped_pattern_is_not_also_banned_outright():
    """A `limit` rule is unreachable if the same injury bans the pattern's joint action.

    The rubric caps lunges at 4 sets/week for patellofemoral pain, which only
    means something if lunges can be selected at all.
    """
    from app.services.movement_taxonomy import MOVEMENT_ATTRIBUTES

    for injury, entry in CONTRAINDICATIONS["injuries"].items():
        banned = set(entry["avoid_joint_actions"])
        for limit in entry.get("limit", []):
            pattern = limit["pattern"]
            actions = set(MOVEMENT_ATTRIBUTES[pattern]["joint_actions"])
            assert not actions & banned, (
                f"'{injury}' caps '{pattern}' at {limit['max_sets_week']} sets but also bans "
                f"{sorted(actions & banned)}, so the cap can never apply"
            )


def test_repeat_fallback_never_relaxes_a_safety_filter(catalog, full_gym):
    """Dropping the no-repeat preference must not smuggle past the injury filter."""
    profile = {**full_gym, "injuries": ["knee_pain_patellofemoral"]}
    actions = forbidden_joint_actions(profile, CONTRAINDICATIONS)
    positions = forbidden_loaded_positions(profile, CONTRAINDICATIONS)
    all_ids = set(catalog)

    # Every id excluded, so the fallback path is guaranteed to be taken.
    candidates = candidates_for_slot(
        {"pattern": "squat", "slot_id": "t"}, profile, catalog, actions, positions, all_ids
    )

    for candidate in candidates:
        assert not set(candidate["joint_actions"]) & actions
        assert not set(candidate["loaded_positions"]) & positions


def test_volume_landmarks_are_reachable(rows):
    """A landmark no exercise contributes to can never fire.

    `side_delts` had this problem: the rubric defined MEV/MAV/MRV for it while
    every shoulder exercise credited `front_delts`, so the one shoulder ceiling
    in the rubric was unenforceable.
    """
    credited = {muscle for r in rows for muscle in r["contribution"]}
    unreachable = sorted(set(VOLUME_LANDMARKS["muscles"]) - credited)
    assert unreachable == [], f"landmarks with no contributing exercise: {unreachable}"


def test_a_realistic_plan_does_not_drown_in_unassessed_warnings(catalog, full_gym):
    """Muscles without a landmark are reported as unassessed — that must stay bounded.

    Not a correctness failure, but a usability one: if most of a report is
    "not assessed", the findings that matter are buried. This asserts the
    current state so that adding catalog muscles without adding landmarks is a
    visible decision rather than a silent drift.
    """
    template = TEMPLATES["upper_lower_4day"]
    plan = {
        "days": [
            {
                "name": day["name"],
                "exercises": [
                    {
                        "exercise_id": filter_candidates(slot, full_gym, catalog, set(), set())[0][
                            "exercise_id"
                        ],
                        "sets": slot["sets"],
                    }
                    for slot in day["slots"]
                ],
            }
            for day in template["days"]
        ]
    }

    issues = check_volume(plan, catalog, VOLUME_LANDMARKS)
    unassessed = [i for i in issues if i["rubric_ref"] == "volume.muscles"]
    assert len(unassessed) <= 12, (
        f"{len(unassessed)} muscles reported as unassessed: "
        f"{sorted(i['location'] for i in unassessed)}"
    )
