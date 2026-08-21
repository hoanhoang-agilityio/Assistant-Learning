"""Shared response base."""

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic_core import CoreSchema


class BaseResponse(BaseModel):
    """Base class for API response models.

    ``from_attributes`` lets a response be built straight from an ORM row.
    """

    model_config = ConfigDict(from_attributes=True)


class StructuredOutput(BaseModel):
    """Base for schemas sent as OpenAI ``response_format``.

    OpenAI's Structured Outputs API rejects any object that omits
    ``additionalProperties: false`` (HTTP 400, ``invalid_json_schema``) and
    requires every key in ``properties`` to also appear in ``required``.
    ``extra='forbid'`` produces the first; the JSON-schema hook produces the
    second without taking Python defaults away, so ``ProfileExtraction()`` in
    tests still constructs.
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Emit the closed, fully-required object OpenAI's API will accept."""
        json_schema = handler(core_schema)
        _close_openai_object(json_schema)
        for definition in json_schema.get("$defs", {}).values():
            if isinstance(definition, dict):
                _close_openai_object(definition)
        return json_schema


def _close_openai_object(schema: dict[str, Any]) -> None:
    """Set ``additionalProperties: false`` and require every property.

    Args:
        schema: One JSON-schema object, mutated in place.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    schema["additionalProperties"] = False
    schema["required"] = list(properties)
    for spec in properties.values():
        if isinstance(spec, dict):
            spec.pop("default", None)
