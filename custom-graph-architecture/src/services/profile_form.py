"""The profile form: which fields it asks for, and whether what came back is storable."""

import json
from enum import Enum
from types import UnionType
from typing import Any, TypedDict, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt
from pydantic import ValidationError
from pydantic.fields import FieldInfo

from src.schemas import UserProfile
from src.services.profile import missing_profile_fields

CHOICE = "choice"
INTEGER = "integer"
NUMBER = "number"

_UNITS = ("cm", "kg")


class ProfileFormField(TypedDict):
    """One field the form asks for."""

    name: str
    label: str
    kind: str
    options: list[str]
    minimum: float | None
    maximum: float | None
    required: bool
    description: str


def _base_type(annotation: Any) -> Any:
    """The type a field carries once ``| None`` is set aside."""

    if get_origin(annotation) is UnionType:
        return next(
            (arg for arg in get_args(annotation) if arg is not type(None)), annotation
        )
    return annotation


def _kind(annotation: Any) -> str | None:
    """What kind of input a field needs, or None when a form cannot ask for it."""

    base = _base_type(annotation)
    if isinstance(base, type) and issubclass(base, Enum):
        return CHOICE
    if base is int:
        return INTEGER
    if base is float:
        return NUMBER
    return None


# The fields a form can ask for at all: the numbers and the fixed choices. Derived
# rather than listed, so a field added to the model is asked for without being named
# again here, and one the form has no input for is never asked for at all.
FORM_FIELDS: tuple[str, ...] = tuple(
    name
    for name, field in UserProfile.model_fields.items()
    if _kind(field.annotation) is not None
)


def _label(name: str) -> str:
    """A field's name as the form shows it."""

    words = name.split("_")
    if words[-1] in _UNITS:
        return f"{' '.join(words[:-1]).capitalize()} ({words[-1]})"
    return " ".join(words).capitalize()


def _options(annotation: Any) -> list[str]:
    """The values a choice field accepts, in declaration order."""

    base = _base_type(annotation)
    if isinstance(base, type) and issubclass(base, Enum):
        return [str(member.value) for member in base]
    return []


def _limit(field: FieldInfo, *kinds: type) -> float | None:
    """The first bound of the given kinds declared on a field."""

    for constraint in field.metadata:
        for kind in kinds:
            if isinstance(constraint, kind):
                return float(getattr(constraint, kind.__name__.lower()))
    return None


def _form_field(name: str) -> ProfileFormField:
    """One field of the form, read off the model that defines it."""

    field = UserProfile.model_fields[name]
    return ProfileFormField(
        name=name,
        label=_label(name),
        kind=str(_kind(field.annotation)),
        options=_options(field.annotation),
        minimum=_limit(field, Ge, Gt),
        maximum=_limit(field, Le, Lt),
        required=field.is_required(),
        description=field.description or "",
    )


def profile_form_fields(
    profile: dict | None, draft: dict | None = None
) -> list[ProfileFormField]:
    """The form to show: every required field still missing, plus whatever the user already stated."""

    wanted = set(missing_profile_fields(profile)) | {
        name for name, value in (draft or {}).items() if value is not None
    }
    return [_form_field(name) for name in FORM_FIELDS if name in wanted]


def _as_mapping(reply: object) -> dict:
    """A submission as sent, whether the caller posted it as fields or as JSON text."""

    if isinstance(reply, dict):
        return reply
    if isinstance(reply, str):
        try:
            decoded = json.loads(reply)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def submitted_values(reply: object) -> dict[str, Any]:
    """The field values a form submission carries, ignoring anything that is not one."""

    return {
        name: value
        for name, value in _as_mapping(reply).items()
        if name in UserProfile.model_fields and value not in (None, "")
    }


def _errors(error: ValidationError) -> dict[str, str]:
    """One message per field the submission got wrong."""

    return {
        str(detail["loc"][0]): detail["msg"]
        for detail in error.errors()
        if detail["loc"]
    }


def validate_profile_submission(
    profile: dict | None, submitted: dict[str, Any]
) -> tuple[dict, dict[str, str]]:
    """The complete profile a submission adds up to, or the field errors keeping it from being one."""

    candidate = {**(profile or {}), **submitted}
    try:
        return UserProfile.model_validate(candidate).model_dump(mode="json"), {}
    except ValidationError as error:
        return {}, _errors(error)


__all__ = [
    "CHOICE",
    "FORM_FIELDS",
    "INTEGER",
    "NUMBER",
    "ProfileFormField",
    "profile_form_fields",
    "submitted_values",
    "validate_profile_submission",
]
