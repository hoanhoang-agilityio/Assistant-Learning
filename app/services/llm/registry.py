"""LLM model registry with pre-initialized instances."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.configs.config import (
    settings,
)

_TOKEN_LIMIT: dict[str, Any] = {"max_completion_tokens": settings.MAX_TOKENS}
_API_KEY = SecretStr(settings.OPENAI_API_KEY)


class LLMRegistry:
    """LLM model registry with pre-initialized instances."""

    LLMS: list[dict[str, Any]] = [
        {
            "name": "gpt-5-mini",
            "llm": ChatOpenAI(
                model="gpt-5-mini",
                api_key=_API_KEY,
                model_kwargs=_TOKEN_LIMIT,
                reasoning={"effort": "low"},
            ),
        },
        {
            "name": "gpt-5.4",
            "llm": ChatOpenAI(
                model="gpt-5",
                api_key=_API_KEY,
                model_kwargs=_TOKEN_LIMIT,
                reasoning={"effort": "medium"},
            ),
        },
        {
            "name": "gpt-5.4-nano",
            "llm": ChatOpenAI(
                model="gpt-5.4-nano",
                api_key=_API_KEY,
                model_kwargs=_TOKEN_LIMIT,
                reasoning={"effort": "low"},
            ),
        },
        {
            "name": "gpt-5",
            "llm": ChatOpenAI(
                model="gpt-5",
                api_key=_API_KEY,
                model_kwargs=_TOKEN_LIMIT,
            ),
        },
    ]

    @classmethod
    def get_llm(cls, model_name: str, **kwargs) -> BaseChatModel:
        """Get an LLM by name with optional argument overrides.

        When kwargs are provided a fresh ChatOpenAI instance is returned with
        those overrides applied, leaving the shared registry entry untouched.

        Args:
            model_name: Name of the model to retrieve.
            **kwargs: Optional arguments to override default model configuration.

        Returns:
            BaseChatModel instance.

        Raises:
            ValueError: If model_name is not found in LLMS.
        """
        model_entry = next((m for m in cls.LLMS if m["name"] == model_name), None)

        if not model_entry:
            available = ", ".join(m["name"] for m in cls.LLMS)
            raise ValueError(
                f"model '{model_name}' not found in registry. available models: {available}"
            )

        if kwargs:
            return ChatOpenAI(model=model_name, api_key=_API_KEY, **kwargs)

        return model_entry["llm"]

    @classmethod
    def get_all_llm_names(cls) -> list[str]:
        """Return all registered model names in order.

        Returns:
            List of model name strings.
        """
        return [e["name"] for e in cls.LLMS]

    @classmethod
    def get_model_by_index(cls, index: int) -> dict[str, Any]:
        """Return the model entry at a specific index, wrapping to 0 if out of range.

        Args:
            index: Index into LLMS.

        Returns:
            Model entry dict.
        """
        if 0 <= index < len(cls.LLMS):
            return cls.LLMS[index]
        return cls.LLMS[0]
