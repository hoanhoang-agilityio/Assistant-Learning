"""Shared pytest configuration.

The suite covers the ``app/`` package. Fixtures live in the test module that
uses them; what is here is the one boundary several modules have to stub the
same way.

The QA agent holds a chat model directly — ``create_agent`` needs one — so
replacing ``llm_service`` no longer keeps that branch off the network. Every
test that can reach ``general_qa`` patches ``_qa_model`` with the fake below
instead.
"""

from collections.abc import Callable
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeChatModel(BaseChatModel):
    """A chat model that answers from a script instead of the network.

    ``bind_tools`` returns ``self``: the agent binds its tools at build time, so
    a fake that raised there would fail before any test ran. What the model does
    with them is decided by ``responses``.
    """

    responses: list[AIMessage] = [AIMessage(content="an answer")]
    on_call: Callable[[], None] | None = None
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        """Identify the model in traces and error messages."""
        return "fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeChatModel":
        """Accept tools and change nothing."""
        return self

    def _next(self, messages: list[BaseMessage]) -> ChatResult:
        """Record the call and return the next scripted response.

        The last response repeats once the script runs out, so a test that only
        cares about the first turn does not have to pad it.

        Args:
            messages: What the agent sent this call.

        Returns:
            The scripted result for this call.
        """
        self.calls.append(list(messages))
        if self.on_call is not None:
            self.on_call()
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Answer synchronously."""
        return self._next(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Answer asynchronously — the path the agent actually takes."""
        return self._next(messages)


def stub_qa_model(monkeypatch, model: FakeChatModel | None = None) -> FakeChatModel:
    """Point the QA agent at a fake model, and its fallbacks at nothing.

    Must run before ``build_qa_agent()``: the agent resolves its model once, at
    build time.

    Args:
        monkeypatch: The pytest fixture doing the patching.
        model: The fake to install. A default one is built when omitted.

    Returns:
        The installed fake, so a test can read ``calls`` off it.
    """
    fake = model or FakeChatModel()
    monkeypatch.setattr("app.core.langgraph.agents.qa.graph._qa_model", lambda: fake)
    monkeypatch.setattr("app.core.langgraph.agents.qa.graph._fallback_models", list)
    return fake
