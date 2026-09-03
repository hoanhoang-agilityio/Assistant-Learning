"""Tests for conversation naming: what the sidebar shows, and what it keeps showing.

The whole point of the feature is a sidebar label that survives a reload and a fresh
login, which means the name has to end up in the ``session`` row and nowhere else. These
tests pin the two halves of that: the placeholder is stored before the turn runs, and the
generated title replaces it — or, when the model cannot be reached, does not.
"""

import asyncio
import sys
import uuid

import pytest

from src.configs.config import settings
from src.models.user import User
from src.schemas import Message, SessionTitle
from src.services.auth import auth_service
from src.services.database import session_factory
from src.services.session_naming import (
    PLACEHOLDER_MAX_CHARS,
    name_session,
)

naming = sys.modules[name_session.__module__]


class _FakeStructuredModel:
    """Stands in for the structured-output call: one scripted title, or a raised error."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls = 0

    def with_retry(self, **_: object) -> "_FakeStructuredModel":
        return self

    async def ainvoke(self, _messages: list) -> object:
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _FakeChatModel:
    """Stands in for ``chat_model()``: serves the one structured call the service makes."""

    def __init__(self, structured: _FakeStructuredModel) -> None:
        self.structured = structured

    def with_structured_output(self, _schema: type) -> _FakeStructuredModel:
        return self.structured


class _FakeAuthService:
    """Records what naming asked the database to do, and whether the claim was won."""

    def __init__(
        self, *, claimed: bool = True, claim_error: Exception | None = None
    ) -> None:
        self.claimed = claimed
        self.claim_error = claim_error
        self.claims: list[tuple[str, str]] = []
        self.renames: list[tuple[str, str]] = []

    async def claim_unnamed_session(self, session_id: str, name: str) -> bool:
        if self.claim_error is not None:
            raise self.claim_error
        self.claims.append((session_id, name))
        return self.claimed

    async def update_session_name(self, session_id: str, name: str) -> None:
        self.renames.append((session_id, name))


@pytest.fixture
def names(monkeypatch: pytest.MonkeyPatch):
    """Wire naming to a recording database and a scripted model."""

    def use(
        outcome: object,
        *,
        claimed: bool = True,
        claim_error: Exception | None = None,
    ) -> tuple[_FakeAuthService, _FakeStructuredModel]:
        service = _FakeAuthService(claimed=claimed, claim_error=claim_error)
        structured = _FakeStructuredModel(outcome)
        monkeypatch.setattr(naming, "auth_service", service)
        monkeypatch.setattr(
            naming, "chat_model", lambda **_: _FakeChatModel(structured)
        )
        return service, structured

    return use


async def _settle() -> None:
    """Wait for the detached title task, which the turn deliberately does not await."""
    await asyncio.gather(*list(naming._background_tasks))


def _turn(text: str) -> list[Message]:
    """One request's worth of messages."""
    return [Message(role="user", content=text)]


async def test_a_placeholder_is_stored_before_the_turn_runs(names) -> None:
    """The sidebar draws while the graph is still working, so a conversation with no name
    yet would sit there as "New chat" for the length of the turn."""
    service, _ = names(SessionTitle(title="Cutting plan"))

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))

    assert service.claims == [("s-1", "I want to cut to 75 kg")]


async def test_a_long_first_message_is_cut_down_to_a_label(names) -> None:
    """A placeholder is a sidebar row, not a transcript: the untruncated message would
    push every other row's text out of view."""
    service, _ = names(SessionTitle(title="Cutting plan"))

    await name_session("s-1", "", _turn("word " * 100))

    assert len(service.claims[0][1]) <= PLACEHOLDER_MAX_CHARS


async def test_the_generated_title_replaces_the_placeholder(names) -> None:
    """The feature the user asked for: the stored name is a summary of the conversation,
    not the first 40 characters of it."""
    service, _ = names(SessionTitle(title="Cutting plan for 75 kg"))

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))
    await _settle()

    assert service.renames == [("s-1", "Cutting plan for 75 kg")]


async def test_a_named_conversation_is_left_alone(names) -> None:
    """Naming runs on every turn, so a conversation the user renamed by hand would be
    overwritten on its next message if this guard went missing."""
    service, structured = names(SessionTitle(title="Cutting plan"))

    await name_session("s-1", "Leg day", _turn("what about squats"))
    await _settle()

    assert service.claims == []
    assert structured.calls == 0


async def test_only_the_caller_that_wins_the_claim_calls_the_model(names) -> None:
    """Two workers can take the first turn of the same conversation at once. Both firing
    a title call spends two inferences and lets the loser's answer win the last write."""
    _, structured = names(SessionTitle(title="Cutting plan"), claimed=False)

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))
    await _settle()

    assert structured.calls == 0


async def test_a_failed_title_call_leaves_the_placeholder(names) -> None:
    """A name is cosmetic. Losing the model must cost the nicer label and not the row,
    or the conversation goes back to being unnamed and gets re-claimed every turn."""
    service, _ = names(RuntimeError("model unavailable"))

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))
    await _settle()

    assert service.claims == [("s-1", "I want to cut to 75 kg")]
    assert service.renames == []


async def test_a_database_failure_does_not_fail_the_turn(names) -> None:
    """``name_session`` is awaited inside the chat endpoint. Anything it raises would turn
    a working answer into a 500."""
    names(SessionTitle(title="Cutting plan"), claim_error=RuntimeError("db down"))

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))


async def test_a_turn_with_nothing_the_user_said_is_not_named(names) -> None:
    """Naming a conversation after a system message would put prompt text in the sidebar."""
    service, structured = names(SessionTitle(title="Cutting plan"))

    await name_session("s-1", "", [Message(role="system", content="context")])
    await _settle()

    assert service.claims == []
    assert structured.calls == 0


async def test_naming_can_be_switched_off(
    names, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deployment without an LLM budget for it still has to be able to serve chat."""
    monkeypatch.setattr(settings, "SESSION_NAMING_ENABLED", False)
    service, structured = names(SessionTitle(title="Cutting plan"))

    await name_session("s-1", "", _turn("I want to cut to 75 kg"))

    assert service.claims == []
    assert structured.calls == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Cutting plan"', "Cutting plan"),
        ("Cutting plan.", "Cutting plan"),
        ("Title: cutting plan", "Title: cutting plan"),
        ("Cutting   plan\n", "Cutting plan"),
    ],
)
def test_a_title_is_normalized_into_a_label(raw: str, expected: str) -> None:
    """The model is asked for a bare title and sometimes returns a quoted sentence.
    Stripping it here means the sidebar never has to."""
    assert SessionTitle(title=raw).title == expected


def test_an_answer_instead_of_a_title_is_rejected() -> None:
    """A model that replies to the message rather than naming it would put a paragraph in
    the sidebar. Rejecting it leaves the placeholder, which is a usable name."""
    with pytest.raises(ValueError, match="at most 60 characters"):
        SessionTitle(title="Here is a full training plan " * 5)


def test_an_empty_title_is_rejected() -> None:
    """An empty name is what marks a conversation unnamed, so storing one would put the
    row back in the claim queue on every turn."""
    with pytest.raises(ValueError, match="printable"):
        SessionTitle(title='"."')


@pytest.mark.integration
async def test_the_claim_is_atomic_against_the_real_database(
    require_postgres: None,
) -> None:
    """The claim is what stops two workers naming one conversation twice, and it is a
    single statement — a construct no fake can check. Run against Postgres it also pins
    the thing the feature exists for: the name is a column, so it is still there for the
    next login to read."""
    user = await auth_service.create_user(
        email=f"naming-{uuid.uuid4().hex}@example.test", password="x"
    )
    assert user.id is not None
    session_id = str(uuid.uuid4())
    await auth_service.create_session(session_id, user.id)

    try:
        first, second = await asyncio.gather(
            auth_service.claim_unnamed_session(session_id, "first"),
            auth_service.claim_unnamed_session(session_id, "second"),
        )
        assert [first, second].count(True) == 1

        stored = await auth_service.get_session(session_id)
        assert stored is not None
        assert stored.name in {"first", "second"}

        await auth_service.update_session_name(session_id, "Cutting plan for 75 kg")
        reread = await auth_service.get_session(session_id)
        assert reread is not None
        assert reread.name == "Cutting plan for 75 kg"

        listed = await auth_service.get_user_sessions(user.id)
        assert [item.name for item in listed] == ["Cutting plan for 75 kg"]
    finally:
        await auth_service.delete_session(session_id)
        async with session_factory() as db:
            row = await db.get(User, user.id)
            if row is not None:
                await db.delete(row)
                await db.commit()
