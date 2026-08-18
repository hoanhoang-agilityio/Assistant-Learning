"""Which model an agent runs on, and what happens when that model fails.

An agent built with ``create_agent`` holds a model directly, so ``llm_service``
— and the retry and circular fallback built into it — is not on that path. This
module restores both as middleware, reading the same retryable-error set and the
same registry order, so the two paths cannot drift into different failure
behaviour.

One module rather than a copy per agent package. Four agents each deciding
independently which model they run on is four places to update when the registry
changes, and the first one that gets missed is a silent downgrade.
"""

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.configs.config import settings
from app.services.llm.registry import LLMRegistry
from app.services.llm.service import RETRYABLE_ERRORS


def default_model() -> BaseChatModel:
    """Resolve the model an agent runs on.

    One seam, deliberately: it is where the tests replace the network, and the
    only place an agent learns which model it is.

    Returns:
        The configured default chat model.
    """
    return LLMRegistry.get_llm(settings.DEFAULT_LLM_MODEL)


def fallback_models() -> list[BaseChatModel]:
    """Return the other registry models, in registry order.

    Returns:
        Every model except the default, tried in turn when the default fails —
        the same circular fallback ``llm_service`` gives the other callers.
    """
    return [
        LLMRegistry.get_llm(name)
        for name in LLMRegistry.get_all_llm_names()
        if name != settings.DEFAULT_LLM_MODEL
    ]


def resilience_middleware() -> list[AgentMiddleware]:
    """Build the retry and fallback middleware every agent gets.

    Returns:
        Retry, then fallback when there is somewhere to fall back to. The
        fallback middleware requires at least one alternative model, so a
        single-model registry would fail at build time rather than run without a
        fallback it never had.
    """
    middleware: list[AgentMiddleware] = [
        ModelRetryMiddleware(
            max_retries=settings.MAX_LLM_CALL_RETRIES,
            retry_on=RETRYABLE_ERRORS,
        )
    ]

    fallbacks = fallback_models()
    if fallbacks:
        middleware.append(ModelFallbackMiddleware(*fallbacks))

    return middleware


__all__ = ["default_model", "fallback_models", "resilience_middleware"]
