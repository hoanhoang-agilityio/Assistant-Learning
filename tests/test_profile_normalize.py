from core.profile.normalize import (
    merge_profile_sources,
    normalize_extracted_profile,
    resolve_activity_level,
)
from core.profile.schema import Constraints, ExtractedProfile, Goal, Profile


def test_normalize_rounds_measurements() -> None:
    extracted = ExtractedProfile(
        profile=Profile(height_cm=175.44, current_weight_kg=85.555),
    )
    profile = normalize_extracted_profile(extracted)
    assert profile["height_cm"] == 175.4
    assert profile["current_weight_kg"] == 85.6


def test_normalize_extracts_days_per_week() -> None:
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=5))
    profile = normalize_extracted_profile(extracted)
    assert profile["days_per_week"] == 5
    assert "activity_level" not in profile, "activity_level is never a profile field"


def test_normalize_sedentary_days_per_week() -> None:
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=0))
    profile = normalize_extracted_profile(extracted)
    assert profile["days_per_week"] == 0


def test_resolve_activity_level_is_a_pure_function_of_days_per_week() -> None:
    """activity_level is never stored -- it's recomputed on demand from days_per_week."""
    assert resolve_activity_level(5) == "gym_5x_week"
    assert resolve_activity_level(0) == "sedentary"
    assert resolve_activity_level(None) == "gym_3x_week"


def test_normalize_includes_goal_fields() -> None:
    extracted = ExtractedProfile(
        profile=Profile(current_weight_kg=75),
        goal=Goal(goal="fat_loss", target_weight_kg=73),
    )
    profile = normalize_extracted_profile(extracted)
    assert profile["current_weight_kg"] == 75.0
    assert profile["target_weight_kg"] == 73.0
    assert profile["goal"] == "fat_loss"


def test_normalize_resolves_delta_only_extraction_into_target_weight() -> None:
    """A delta-only phrase ("lose 5kg") must resolve into target_weight_kg and never
    persist weight_delta_kg -- see resolve_target_weight."""
    extracted = ExtractedProfile(
        profile=Profile(current_weight_kg=80),
        goal=Goal(goal="fat_loss", weight_delta_kg=-5),
    )
    profile = merge_profile_sources(query="lose 5kg", profile={}, extracted=extracted)
    assert profile["target_weight_kg"] == 75.0
    assert "weight_delta_kg" not in profile


def test_merge_profile_prefers_stored_profile() -> None:
    """Successor to the old `test_merge_profile_prefers_user_profile`, adapted for the
    single flat `profile` seed: non-constraint stored fields must still beat extraction."""
    extracted = ExtractedProfile(profile=Profile(age=40, height_cm=180, sex="male"))
    profile = merge_profile_sources(
        query="test",
        profile={"age": 30, "height_cm": 175},
        extracted=extracted,
    )
    assert profile["age"] == 30
    assert profile["height_cm"] == 175


def test_merge_profile_applies_constraints() -> None:
    extracted = ExtractedProfile()
    profile = merge_profile_sources(
        query="test",
        profile={"days_per_week": 4, "equipment": "gym"},
        extracted=extracted,
    )
    assert profile["days_per_week"] == 4
    assert profile["equipment"] == "gym"


def test_merge_profile_query_overrides_constraints() -> None:
    """Successor to the pre-flatten test of the same name: constraint fields stay the
    *lowest* priority tier even when they arrive pre-merged into one flat `profile` dict --
    a fresh query-text extraction must still override a stale/seeded constraint value."""
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=5))
    profile = merge_profile_sources(
        query="test",
        profile={"days_per_week": 4, "equipment": "gym"},
        extracted=extracted,
    )
    assert profile["days_per_week"] == 5
    assert profile["equipment"] == "gym"
    assert "activity_level" not in profile


def test_merge_profile_sources_preserves_three_tier_precedence() -> None:
    """Regression test for the merge-precedence invariant flagged in the VFS-profile plan:
    flattening `user_profile`/`constraints` into one seed dict must not collapse the three
    original priority tiers into two. In one call: a constraint field (`days_per_week`) is
    the lowest tier and must lose to extraction; a non-constraint stored field (`age`) is the
    highest tier and must beat extraction even though extraction also supplies it.
    """
    extracted = ExtractedProfile(
        profile=Profile(age=99, sex="male"),
        constraints=Constraints(days_per_week=5),
    )
    profile = merge_profile_sources(
        query="test",
        profile={"age": 30, "days_per_week": 4},
        extracted=extracted,
    )
    assert profile["age"] == 30, "stored non-constraint field must beat fresh extraction"
    assert profile["days_per_week"] == 5, "stored constraint field must lose to fresh extraction"
    assert profile["sex"] == "male"
