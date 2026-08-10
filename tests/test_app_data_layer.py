"""Tests for the catalog filter, the template library and the macro maths.

All three are plain functions, so none of this needs a graph, a model or
Postgres — ``filter_candidates`` takes the catalog as an argument precisely so it
can be tested against a fixture.

The properties under test are the design's guarantees:

* a contraindicated exercise cannot reach a candidate list
* sets and reps come from the template, never from anywhere else
* adding a training day changes TDEE, which is why change_plan must recompute
"""

import pytest

from app.services.catalog import (
    filter_candidates,
    forbidden_joint_actions,
    forbidden_loaded_positions,
)
from app.services.nutrition import (
    ACTIVITY_FACTORS,
    calc_macros,
    compute_tdee,
    mifflin_st_jeor,
    split_macros,
)
from app.services.templates import iter_slots
from tests.seed import CONTRAINDICATIONS, TEMPLATES, get_template, query_templates

CATALOG = {
    "bb_back_squat": {
        "exercise_id": "bb_back_squat",
        "name": "Barbell back squat",
        "movement_pattern": "squat",
        "equipment": ["barbell", "rack"],
        "joint_actions": ["knee_flexion_deep", "hip_extension"],
        "loaded_positions": ["knee_end_range"],
        "contribution": {"quads": 1.0},
        "skill_level": 3,
        "fatigue_cost": 5,
    },
    "goblet_squat": {
        "exercise_id": "goblet_squat",
        "name": "Goblet squat",
        "movement_pattern": "squat",
        "equipment": ["dumbbell"],
        "joint_actions": ["knee_extension", "hip_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 1.0},
        "skill_level": 1,
        "fatigue_cost": 2,
    },
    "leg_press": {
        "exercise_id": "leg_press",
        "name": "Leg press",
        "movement_pattern": "squat",
        "equipment": ["leg_press_machine"],
        "joint_actions": ["knee_extension", "hip_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 1.0},
        "skill_level": 1,
        "fatigue_cost": 3,
    },
    "db_bench_press": {
        "exercise_id": "db_bench_press",
        "name": "Dumbbell bench press",
        "movement_pattern": "horizontal_push",
        "equipment": ["dumbbell", "bench"],
        "joint_actions": ["shoulder_horizontal_adduction"],
        "loaded_positions": [],
        "contribution": {"chest": 1.0},
        "skill_level": 1,
        "fatigue_cost": 3,
    },
}

FULL_GYM = {
    "equipment": ["barbell", "rack", "dumbbell", "bench", "leg_press_machine"],
    "level": 3,
    "injuries": [],
}

SQUAT_SLOT = {"slot_id": "la_squat", "pattern": "squat"}


# ---------------------------------------------------------------------------
# Catalog filter
# ---------------------------------------------------------------------------


def test_filter_returns_matching_pattern_only():
    """A slot gets candidates for its own movement pattern and no others."""
    candidates = filter_candidates(SQUAT_SLOT, FULL_GYM, CATALOG, set(), set())
    assert {c["exercise_id"] for c in candidates} == {
        "bb_back_squat",
        "goblet_squat",
        "leg_press",
    }


def test_filter_excludes_equipment_the_user_lacks():
    """Equipment is a subset test, not a preference."""
    home = {"equipment": ["dumbbell"], "level": 3, "injuries": []}
    candidates = filter_candidates(SQUAT_SLOT, home, CATALOG, set(), set())
    assert [c["exercise_id"] for c in candidates] == ["goblet_squat"]


def test_filter_excludes_exercises_above_skill_level():
    """A beginner does not get a candidate they cannot perform safely."""
    beginner = {**FULL_GYM, "level": 1}
    candidates = filter_candidates(SQUAT_SLOT, beginner, CATALOG, set(), set())
    assert "bb_back_squat" not in {c["exercise_id"] for c in candidates}


def test_filter_excludes_contraindicated_exercises():
    """workflow.md 6.2: the injury filter is in the query, not in the prompt."""
    profile = {**FULL_GYM, "injuries": ["knee_pain_patellofemoral"]}
    forbidden = forbidden_joint_actions(profile, CONTRAINDICATIONS)
    positions = forbidden_loaded_positions(profile, CONTRAINDICATIONS)

    candidates = filter_candidates(SQUAT_SLOT, profile, CATALOG, forbidden, positions)

    assert "bb_back_squat" not in {c["exercise_id"] for c in candidates}
    assert {c["exercise_id"] for c in candidates} == {"goblet_squat", "leg_press"}


def test_filter_honours_exclusions():
    """Already-used exercises are kept out so days do not repeat a movement."""
    candidates = filter_candidates(
        SQUAT_SLOT, FULL_GYM, CATALOG, set(), set(), exclude_ids={"goblet_squat"}
    )
    assert "goblet_squat" not in {c["exercise_id"] for c in candidates}


def test_filter_orders_by_fatigue_cost():
    """Ties resolve toward the more recoverable option."""
    candidates = filter_candidates(SQUAT_SLOT, FULL_GYM, CATALOG, set(), set())
    costs = [c["fatigue_cost"] for c in candidates]
    assert costs == sorted(costs)


def test_filter_returns_empty_rather_than_relaxing_a_constraint():
    """No candidate is a reportable conflict, not a reason to drop a filter."""
    bands_only = {"equipment": ["resistance_band"], "level": 3, "injuries": []}
    assert filter_candidates(SQUAT_SLOT, bands_only, CATALOG, set(), set()) == []


def test_unknown_injury_forbids_nothing_here():
    """An unrecognised injury restricts no exercise; the verifier reports it instead."""
    profile = {**FULL_GYM, "injuries": ["lower_back_disc_herniation"]}
    assert forbidden_joint_actions(profile, CONTRAINDICATIONS) == set()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_every_slot_carries_its_own_prescription():
    """workflow.md 6.1: sets, reps and RIR live on the slot, not in a model."""
    for template_id, template in TEMPLATES.items():
        for slot in iter_slots(template):
            assert isinstance(slot["sets"], int), f"{template_id}/{slot['slot_id']}"
            assert len(slot["reps"]) == 2, f"{template_id}/{slot['slot_id']}"
            assert len(slot["rir"]) == 2, f"{template_id}/{slot['slot_id']}"
            assert slot["reps"][0] <= slot["reps"][1]


def test_slot_ids_are_unique_across_the_library():
    """A collision would apply one exercise choice to two different slots."""
    slot_ids = [slot["slot_id"] for t in TEMPLATES.values() for slot in iter_slots(t)]
    assert len(slot_ids) == len(set(slot_ids))


def test_template_day_count_matches_its_declaration():
    """days_per_week is what select_template filters on — it must be true."""
    for template in TEMPLATES.values():
        assert len(template["days"]) == template["days_per_week"]


def test_query_templates_filters_on_all_three_criteria():
    """Days, goal and level are hard filters, and an empty result is meaningful."""
    assert [t["template_id"] for t in query_templates(4, "fat_loss", 2)] == ["upper_lower_4day"]
    assert query_templates(6, "fat_loss", 2) == [], "no 6-day template exists"
    assert query_templates(4, "powerlifting_peak", 2) == [], "no template targets that goal"


def test_every_experience_level_has_a_template():
    """A level with no programme means build_plan cannot serve that user at all.

    `level` lists the experience levels a programme suits, not a ceiling. Both
    templates originally stopped at 2 and 3, which silently locked advanced
    lifters out of every goal.
    """
    for level in range(1, 6):
        assert query_templates(4, "fat_loss", level), f"no 4-day template for level {level}"
        assert query_templates(3, "fat_loss", level), f"no 3-day template for level {level}"


def test_get_template_returns_none_for_an_unknown_id():
    """An unknown id is not an exception — select_template reports it."""
    assert get_template("nope") is None


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------


def test_mifflin_st_jeor_matches_the_published_equation():
    """75 kg, 175 cm, 28 y, male: 10*75 + 6.25*175 - 5*28 + 5 = 1708.75."""
    assert mifflin_st_jeor(75, 175, 28, "male") == pytest.approx(1708.75)


def test_mifflin_st_jeor_female_constant():
    """Same body, female constant: 1708.75 - 5 - 161 = 1542.75."""
    assert mifflin_st_jeor(75, 175, 28, "female") == pytest.approx(1542.75)


def test_mifflin_st_jeor_rejects_an_unknown_sex():
    """No silent fallback — the two constants differ by 166 kcal."""
    with pytest.raises(ValueError, match="unsupported sex"):
        mifflin_st_jeor(75, 175, 28, "unspecified")


def test_adding_a_training_day_raises_tdee():
    """workflow.md 9.2: this is why change_plan must recompute macros."""
    bmr = mifflin_st_jeor(75, 175, 28, "male")
    four = compute_tdee(bmr, "sedentary", 4)
    five = compute_tdee(bmr, "sedentary", 5)
    assert five > four
    assert five - four == pytest.approx(bmr * 0.025)


def test_compute_tdee_rejects_an_unknown_activity_level():
    """Defaulting would be wrong by hundreds of calories and look authoritative."""
    with pytest.raises(ValueError, match="unknown activity_level"):
        compute_tdee(1700, "somewhat_active", 4)


def test_activity_factors_are_ordered():
    """A more active life must never produce a lower multiplier."""
    values = [
        ACTIVITY_FACTORS[k] for k in ["sedentary", "light", "moderate", "active", "very_active"]
    ]
    assert values == sorted(values)


def test_split_macros_conserves_calories():
    """Protein, fat and carbs must add back up to the target, within rounding."""
    macros = split_macros(2100, 75)
    total = macros["protein_g"] * 4 + macros["fat_g"] * 9 + macros["carbs_g"] * 4
    assert total == pytest.approx(2100, abs=4)


def test_split_macros_never_returns_negative_carbs():
    """An impossible target clamps; the verifier's kcal floor reports the problem."""
    macros = split_macros(600, 75)
    assert macros["carbs_g"] == 0


def test_calc_macros_applies_the_goal_adjustment():
    """A fat-loss goal produces a target below maintenance, muscle gain above it."""
    profile = {
        "weight_kg": 75,
        "height_cm": 175,
        "age": 28,
        "sex": "male",
        "activity_level": "light",
    }
    cut = calc_macros(profile, sessions_per_week=4, goal="fat_loss")
    gain = calc_macros(profile, sessions_per_week=4, goal="muscle_gain")

    assert cut["kcal"] < cut["tdee"] < gain["kcal"]
    assert cut["goal"] == "fat_loss"
    assert cut["protein_g"] == 150


def test_calc_macros_rejects_an_unknown_goal():
    """An unrecognised goal must not silently become maintenance."""
    profile = {
        "weight_kg": 75,
        "height_cm": 175,
        "age": 28,
        "sex": "male",
        "activity_level": "light",
    }
    with pytest.raises(ValueError, match="unknown goal"):
        calc_macros(profile, sessions_per_week=4, goal="get_shredded")


def test_calc_macros_output_passes_the_macro_rubric():
    """The calculator and the verifier must agree on a normal profile."""
    from app.core.langgraph.agents.verification.checks import check_macro
    from tests.seed import MACRO_RULES

    profile = {
        "weight_kg": 75,
        "height_cm": 175,
        "age": 28,
        "sex": "male",
        "activity_level": "light",
        "injuries": [],
    }
    macros = calc_macros(profile, sessions_per_week=4, goal="fat_loss")
    assert check_macro(macros, profile, MACRO_RULES) == []


# ---------------------------------------------------------------------------
# Accumulating preferences
# ---------------------------------------------------------------------------


def test_a_new_preference_does_not_replace_the_old_ones():
    """The bug this function exists to close.

    Every other profile column answers a question with one answer, so the
    generic ``{**stored, **extracted}`` merge is right for them. Preferences are
    a list wearing a string's clothes: "avoids overhead pressing" and "prefers
    dumbbells" are both true at once, and replacing loses the first the moment
    the second is said.
    """
    from app.services.profile import merge_preferences

    merged = merge_preferences("avoids overhead pressing", "prefers dumbbells")

    assert "avoids overhead pressing" in merged
    assert "prefers dumbbells" in merged


def test_restating_a_preference_does_not_duplicate_it():
    """Said twice in different sessions is still one preference.

    Matching is on normalised text, so it collapses the identical and leaves
    genuinely different wording alone — the same honest limit as the episodic
    deduper, and for the same reason: guessing at near-matches is how a store
    starts editing what the user said.
    """
    from app.services.profile import merge_preferences

    merged = merge_preferences("Prefers dumbbells", "  prefers   DUMBBELLS  ")

    assert merged == "Prefers dumbbells"


def test_preferences_are_capped_and_drop_the_oldest():
    """The field converges, so a bound is enough and no compaction is needed."""
    from app.services.profile import _MAX_PREFERENCES, merge_preferences

    stored = "; ".join(f"item {index}" for index in range(_MAX_PREFERENCES))
    merged = merge_preferences(stored, "the newest thing")

    items = merged.split("; ")
    assert len(items) == _MAX_PREFERENCES
    assert items[-1] == "the newest thing"
    assert "item 0" not in items, "the cap dropped the newest instead of the oldest"


def test_several_preferences_stated_at_once_are_kept_apart():
    """One turn can state two things, and they must not fuse into one item."""
    from app.services.profile import merge_preferences

    merged = merge_preferences("", "hates burpees; prefers morning sessions")

    assert merged.split("; ") == ["hates burpees", "prefers morning sessions"]


def test_an_empty_statement_leaves_the_stored_preferences_alone():
    """A turn that mentions no preference must not blank the column."""
    from app.services.profile import merge_preferences

    assert merge_preferences("hates burpees", "") == "hates burpees"
    assert merge_preferences("hates burpees", None) == "hates burpees"
