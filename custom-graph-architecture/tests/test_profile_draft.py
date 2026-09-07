"""Tests for the profile draft: reading back what the user already said, to pre-fill the form."""

import sys

import pytest
from langchain_core.messages import HumanMessage

from src.services.profile_draft import ProfileDraft, draft_profile
from src.services.profile_form import FORM_FIELDS

draft_module = sys.modules[draft_profile.__module__]


class _FakeStructuredModel:
    """Stands in for the structured-output call: one scripted draft, or a raised error."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    def with_retry(self, **_: object) -> "_FakeStructuredModel":
        return self

    async def ainvoke(self, _messages: list) -> object:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _FakeChatModel:
    """Stands in for ``chat_model()``: serves the one structured call the service makes."""

    def __init__(self, structured: _FakeStructuredModel) -> None:
        self.structured = structured

    def with_structured_output(self, _schema: type) -> _FakeStructuredModel:
        return self.structured


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch):
    """Serve a scripted draft instead of calling the model."""

    def use(outcome: object) -> None:
        monkeypatch.setattr(
            draft_module,
            "chat_model",
            lambda **_: _FakeChatModel(_FakeStructuredModel(outcome)),
        )

    return use


def test_the_draft_can_carry_every_field_the_form_asks_for() -> None:
    """A field the form asks for but the draft cannot hold is a field the user has to
    retype even though they already said it."""
    assert set(FORM_FIELDS) <= set(ProfileDraft.model_fields)


def test_no_field_of_the_draft_is_required() -> None:
    """A conversation that mentions nothing about the user is a valid draft — demanding
    a field here would turn a silent opening message into an extraction failure."""
    assert not any(field.is_required() for field in ProfileDraft.model_fields.values())


async def test_what_the_user_stated_comes_back(reads) -> None:
    """The complaint this answers: a user who opened with their age, height and weight
    should see them on the form, not be asked for them again."""
    reads(ProfileDraft(age=27, sex="MALE", height_cm=178.0, target_weight_kg=75.0))

    draft = await draft_profile([HumanMessage(content="I'm 27, male, 178cm")])

    assert draft["age"] == 27
    assert draft["sex"] == "MALE"
    assert draft["target_weight_kg"] == 75.0


async def test_what_the_user_did_not_state_is_left_out(reads) -> None:
    """An unset field must not reach the form as a filled-in None, which would render as
    an answered question the user then has to notice and correct."""
    reads(ProfileDraft(age=27))

    draft = await draft_profile([HumanMessage(content="I'm 27")])

    assert draft == {"age": 27}


async def test_a_failed_read_costs_the_pre_fill_and_not_the_turn(reads) -> None:
    """The draft is a convenience. If the model call fails the user still gets the form,
    blank, rather than an error on a request that can still be served."""
    reads(RuntimeError("model unavailable"))

    assert await draft_profile([HumanMessage(content="I'm 27")]) == {}
