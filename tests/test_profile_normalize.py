from core.profile.normalize import merge_profile_sources, normalize_extracted_profile
from core.profile.schema import Constraints, ExtractedProfile, Goal, Profile


def test_normalize_rounds_measurements() -> None:
    extracted = ExtractedProfile(
        profile=Profile(height_cm=175.44, current_weight_kg=85.555),
    )
    profile = normalize_extracted_profile(extracted)
    assert profile["height_cm"] == 175.4
    assert profile["current_weight_kg"] == 85.6


def test_normalize_derives_activity_from_days_per_week() -> None:
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=5))
    profile = normalize_extracted_profile(extracted)
    assert profile["activity_level"] == "gym_5x_week"
    assert profile["days_per_week"] == 5


def test_normalize_sedentary_days_per_week() -> None:
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=0))
    profile = normalize_extracted_profile(extracted)
    assert profile["activity_level"] == "sedentary"
    assert profile["days_per_week"] == 0


def test_normalize_includes_goal_fields() -> None:
    extracted = ExtractedProfile(
        profile=Profile(current_weight_kg=75),
        goal=Goal(goal="fat_loss", target_weight_kg=73),
    )
    profile = normalize_extracted_profile(extracted)
    assert profile["current_weight_kg"] == 75.0
    assert profile["target_weight_kg"] == 73.0
    assert profile["goal"] == "fat_loss"


def test_merge_profile_prefers_user_profile() -> None:
    extracted = ExtractedProfile(profile=Profile(age=40, height_cm=180, sex="male"))
    profile = merge_profile_sources(
        query="test",
        user_profile={"age": 30, "height_cm": 175},
        constraints={},
        extracted=extracted,
    )
    assert profile["age"] == 30
    assert profile["height_cm"] == 175


def test_merge_profile_applies_constraints() -> None:
    extracted = ExtractedProfile()
    profile = merge_profile_sources(
        query="test",
        user_profile={},
        constraints={"days_per_week": 4, "equipment": "gym"},
        extracted=extracted,
    )
    assert profile["days_per_week"] == 4
    assert profile["equipment"] == "gym"


def test_merge_profile_query_overrides_constraints() -> None:
    extracted = ExtractedProfile(constraints=Constraints(days_per_week=5))
    profile = merge_profile_sources(
        query="test",
        user_profile={},
        constraints={"days_per_week": 4, "equipment": "gym"},
        extracted=extracted,
    )
    assert profile["days_per_week"] == 5
    assert profile["activity_level"] == "gym_5x_week"
