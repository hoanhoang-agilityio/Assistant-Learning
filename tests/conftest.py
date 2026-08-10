"""Shared pytest configuration.

The suite covers the ``app/`` package. Fixtures live in the test module that
uses them; what is here is the one boundary several modules have to stub the
same way.

Every agent now holds a chat model directly — ``create_agent`` needs one — so
replacing ``llm_service`` no longer keeps the suite off the network. All four
resolve it through ``app.core.langgraph.models``, which is why :func:`stub_model`
below is one patch rather than one per package: an agent added later is stubbed
by the same call, instead of reaching the network until someone notices.
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


def stub_model(monkeypatch, model: FakeChatModel | None = None) -> FakeChatModel:
    """Point every agent at a fake model, and their fallbacks at nothing.

    Patches the registry rather than ``app.core.langgraph.models``, and that is
    not incidental. Four modules do ``from ...models import default_model``,
    which binds the function into their own namespace at import time — patching
    the definition would leave every one of them calling the real thing and
    reaching the network. ``LLMRegistry`` is the seam underneath all of them.

    Must run before the agent is built: ``create_agent`` resolves its model once,
    at build time. Anything already built and cached in
    ``app.core.langgraph.agents`` will not pick this up — call
    :func:`reset_agents` first.

    Args:
        monkeypatch: The pytest fixture doing the patching.
        model: The fake to install. A default one is built when omitted.

    Returns:
        The installed fake, so a test can read ``calls`` off it.
    """
    from app.core.configs.config import settings
    from app.services.llm.registry import LLMRegistry

    fake = model or FakeChatModel()
    monkeypatch.setattr(LLMRegistry, "get_llm", staticmethod(lambda *_a, **_kw: fake))
    # One name means `fallback_models()` finds nothing to fall back to, so a
    # scripted failure surfaces instead of being retried against a second fake.
    monkeypatch.setattr(
        LLMRegistry, "get_all_llm_names", staticmethod(lambda: [settings.DEFAULT_LLM_MODEL])
    )
    return fake


def reset_agents() -> None:
    """Drop the compiled-agent cache so the next build sees a stubbed model.

    The registry caches by design — under a supervisor the same agent may be
    invoked several times in one turn — which makes it a fixture that leaks
    between tests unless it is cleared.
    """
    from app.core.langgraph import agents

    agents._built.clear()


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    """Build an assistant message that calls one tool.

    Args:
        name: Tool to call.
        args: Arguments to call it with.
        call_id: Id the resulting ``ToolMessage`` answers.

    Returns:
        The message to script into :class:`FakeChatModel`.
    """
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )
