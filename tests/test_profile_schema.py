import pytest
from pydantic import ValidationError

from core.profile.schema import Constraints, ExtractedProfile, Profile


def test_extracted_profile_defaults_to_empty_sections() -> None:
    extracted = ExtractedProfile()
    assert extracted.profile.age is None
    assert extracted.goal.goal is None
    assert extracted.constraints.days_per_week is None


def test_extracted_profile_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"profile": {"age": 30, "weight_lbs": 180}})


def test_profile_field_constraints() -> None:
    with pytest.raises(ValidationError):
        Profile(age=12)
    with pytest.raises(ValidationError):
        Profile(height_cm=-1)


def test_constraints_days_per_week_bounds() -> None:
    with pytest.raises(ValidationError):
        Constraints(days_per_week=7)
    constraints = Constraints(days_per_week=0)
    assert constraints.days_per_week == 0


def test_json_schema_has_nested_sections() -> None:
    schema = ExtractedProfile.model_json_schema()
    assert "profile" in schema["properties"]
    assert "goal" in schema["properties"]
    assert "constraints" in schema["properties"]
