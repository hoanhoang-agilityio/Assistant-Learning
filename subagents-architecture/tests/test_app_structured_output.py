"""OpenAI rejects a ``response_format`` schema that is not a closed object.

The 400 is ``invalid_json_schema``: every object must set
``additionalProperties: false`` and list every property in ``required``. These
assertions pin that on every schema we send as structured output, so a new
field cannot silently reopen the object.
"""

from typing import Any

from app.schemas.chat import SessionSummary, SessionTitle
from app.schemas.graph import IntentDecision, PlanChanges, ProfileExtraction

_STRUCTURED_OUTPUT_MODELS = (
    IntentDecision,
    PlanChanges,
    ProfileExtraction,
    SessionTitle,
    SessionSummary,
)


def test_structured_output_schemas_are_closed_objects() -> None:
    """A missing ``additionalProperties: false`` is a 400 before the model runs."""
    for model in _STRUCTURED_OUTPUT_MODELS:
        _assert_closed_object(model.model_json_schema())


def _assert_closed_object(schema: dict[str, Any]) -> None:
    """Fail if this object, or any nested ``$defs`` object, is open.

    Args:
        schema: A JSON schema produced by ``model_json_schema``.
    """
    properties = schema.get("properties")
    if isinstance(properties, dict):
        assert schema.get("additionalProperties") is False
        assert list(schema.get("required", [])) == list(properties)
        for spec in properties.values():
            if isinstance(spec, dict):
                assert "default" not in spec
    for definition in schema.get("$defs", {}).values():
        if isinstance(definition, dict):
            _assert_closed_object(definition)
