"""What the user is asked to approve before a stored profile field is overwritten.

The real ``user_agent`` — its real tools and the real ``HumanInTheLoopMiddleware`` — under
a scripted model, because the wording this pins down lives in the wiring between them.
Without a ``description`` the pause reads ``Tool: update_user_profile Args: {...}``.
"""

from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import Field

import src.agents.user as user_module
import src.services.memory as memory_service
from src.agents.user import user_agent
from src.runtime import MemoryScope, namespace_for
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from src.services.profile import PROFILE_KEY
from src.services.profile_presentation import PROFILE_UPDATED

USER_ID = "user-profile-update"
CONFIG = {"configurable": {"thread_id": "profile-update"}}

QUERY = "update my profile to train 5 days per week"

STORED = {
    "age": 30,
    "sex": "MALE",
    "height_cm": 171.0,
    "current_weight_kg": 75.0,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}


class _ScriptedModel(BaseChatModel):
    """Plays a fixed script of replies, and takes tools without needing to choose between them."""

    replies: list[AIMessage] = Field(default_factory=list)
    served: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        reply = self.replies[len(self.served)]
        self.served.append(reply)
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedModel":
        return self


def _overwrite_call() -> list[AIMessage]:
    """A write to a field the profile already holds a value for."""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "update_user_profile",
                    "args": {"field": "training_days_per_week", "value": 5},
                    "id": "call_1",
                }
            ],
        ),
        AIMessage(content="Saved."),
    ]


@pytest.fixture
async def run(monkeypatch: pytest.MonkeyPatch):
    """The real user agent as a one-node graph, over a store already holding a profile."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    store = await runtime.store()
    await store.aput(namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY, STORED)

    model = _ScriptedModel(replies=_overwrite_call())
    monkeypatch.setattr(user_module, "chat_model", lambda **_: model)
    user_module.build_user_agent.cache_clear()

    builder = StateGraph(GraphState)
    builder.add_node("user_agent", user_agent)
    builder.add_edge(START, "user_agent")
    builder.add_edge("user_agent", END)

    yield builder.compile(checkpointer=await runtime.checkpointer()), store

    user_module.build_user_agent.cache_clear()
    await runtime.close()


async def _stored(store) -> dict:
    entry = await store.aget(namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY)
    return entry.value


# --- The pause ----------------------------------------------------------------------------


async def test_an_overwrite_stops_the_run(run) -> None:
    """The pause has to reach the caller rather than be swallowed by the node's own fallback."""
    graph, _ = run

    result = await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    assert len(result["__interrupt__"]) == 1


async def test_the_pause_asks_in_the_users_own_terms(run) -> None:
    """No tool name, no field names, no JSON — the change as the user would describe it."""
    graph, _ = run

    result = await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    question = result["__interrupt__"][0].value["action_requests"][0]["description"]
    assert question == (
        "Got it! I'll save these details to your profile:\n"
        "\n"
        "- Training: 5 days/week\n"
        "\n"
        "Save these details?"
    )


async def test_nothing_is_written_while_the_run_is_still_asking(run) -> None:
    """The approval is what authorizes the write, so it cannot have happened yet."""
    graph, store = run

    await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    assert await _stored(store) == STORED


# --- The decision -------------------------------------------------------------------------


async def test_approval_writes_the_field(run) -> None:
    graph, store = run
    await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    await graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), CONFIG)

    assert await _stored(store) == {**STORED, "training_days_per_week": 5}


async def test_the_turn_confirms_the_change_and_nothing_else(run) -> None:
    """Not the tool it called, not the field it passed — one business-level line."""
    graph, _ = run
    await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    result = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "approve"}]}), CONFIG
    )

    assert result["messages"][-1].content == PROFILE_UPDATED


async def test_a_rejected_change_keeps_the_agents_own_words(run) -> None:
    """Nothing was written, so the confirmation line would be a lie."""
    graph, store = run
    await graph.ainvoke(initial_state(QUERY, USER_ID), CONFIG)

    result = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "reject", "message": "not right"}]}),
        CONFIG,
    )

    assert await _stored(store) == STORED
    assert result["messages"][-1].content != PROFILE_UPDATED
