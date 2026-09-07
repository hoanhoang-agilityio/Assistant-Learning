"""Where naming sits inside a chat turn, which is the part the endpoint decides.

Both chat routes name the conversation before they hand the turn to the graph. For the
streaming route that has to happen outside the event generator: a generator body does not
start until the client reads the first frame, so naming from inside it would leave a
conversation the user abandoned mid-answer sitting unnamed in the sidebar it was started
from — and every later turn would re-open the same race.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.v1 import chat as chat_route
from src.api.v1.auth import get_current_session
from src.configs.config import settings
from src.enums import StreamEventType
from src.main import app
from src.schemas import ChatRequest, Message, StreamResponse

API = settings.API_V1_STR
SESSION = SimpleNamespace(id="s-1", user_id=1, name="", username=None)
REPLY = "Here is your plan."


class _Recorder:
    """Stands in for ``name_session``, recording each call and when it happened."""

    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.calls: list[tuple[str, str, list[Message]]] = []

    async def __call__(
        self, session_id: str, session_name: str, messages: list[Message]
    ) -> None:
        self.log.append("named")
        self.calls.append((session_id, session_name, messages))


class _FakeRuntime:
    """Stands in for the graph: one reply, and a note of when it was asked for."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def get_response(
        self, *_args: object, **_kwargs: object
    ) -> tuple[list, None]:
        self.log.append("ran")
        return [Message(role="assistant", content=REPLY)], None

    async def get_stream_response(
        self, *_args: object, **_kwargs: object
    ) -> AsyncGenerator[StreamResponse]:
        self.log.append("ran")
        yield StreamResponse(type=StreamEventType.MESSAGE, content=REPLY)


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch):
    """A client whose chat turns hit fakes, plus the order the two of them ran in."""
    log: list[str] = []
    recorder = _Recorder(log)
    monkeypatch.setattr(chat_route, "name_session", recorder)
    monkeypatch.setattr(chat_route, "langgraph_runtime", _FakeRuntime(log))
    app.dependency_overrides[get_current_session] = lambda: SESSION
    with TestClient(app) as client:
        yield client, recorder, log
    app.dependency_overrides.clear()


def test_a_turn_is_named_before_the_graph_runs(turn) -> None:
    """A turn can run for minutes. Naming after it would leave the sidebar row unlabelled
    for the whole time the user is waiting on the answer they just asked for."""
    client, recorder, log = turn

    response = client.post(
        f"{API}/chat",
        json={"messages": [{"role": "user", "content": "plan me a week"}]},
    )

    assert response.status_code == 200, response.text
    assert log == ["named", "ran"]
    assert recorder.calls[0][:2] == ("s-1", "")


async def test_a_stream_is_named_before_anything_reads_it(turn) -> None:
    """The reason naming is not inside ``event_source``: a generator body does not run
    until something reads it, so a client that opens the stream and walks away would
    leave the conversation unnamed. Called under the rate-limit decorator rather than
    through the test client, which drives the generator before handing back a response
    and so cannot see the difference."""
    _, _, log = turn

    response = await chat_route.chat_stream.__wrapped__(
        request=None,
        chat_request=ChatRequest(
            messages=[Message(role="user", content="plan me a week")]
        ),
        session=SESSION,
    )

    assert log == ["named"]

    frames = [frame async for frame in response.body_iterator]

    assert log == ["named", "ran"]
    assert any(REPLY in str(frame) for frame in frames)


def test_the_message_the_conversation_is_named_after_is_the_one_sent(turn) -> None:
    """Naming reads the request, not the checkpointer: the graph has not run yet, so a
    name taken from stored history would be taken from an empty conversation."""
    client, recorder, _ = turn

    client.post(
        f"{API}/chat", json={"messages": [{"role": "user", "content": "cut to 75 kg"}]}
    )

    assert [item.content for item in recorder.calls[0][2]] == ["cut to 75 kg"]
