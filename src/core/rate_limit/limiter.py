from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from core.config.settings import Settings, get_settings
from core.rate_limit.context import get_rate_limit_user_id
from core.rate_limit.errors import RateLimitExceededError
from core.rate_limit.pricing import estimate_cost_usd
from core.rate_limit.store import DailyUsage, InMemoryUsageStore, UsageStore


@dataclass(frozen=True)
class RateLimitSnapshot:
    """Serializable view of a user's daily consumption."""

    user_id: str
    day_key: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    daily_max_requests: int
    daily_max_tokens: int
    daily_max_cost_usd: float


class AIRateLimiter:
    """Enforce per-user daily request, token, and estimated cost caps."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: UsageStore | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or InMemoryUsageStore()

    @property
    def enabled(self) -> bool:
        return self._settings.rate_limit_enabled

    def resolve_user_id(self, user_id: str | None) -> str:
        candidate = (user_id or "").strip()
        if candidate:
            return candidate
        return self._settings.rate_limit_default_user_id

    def get_snapshot(self, user_id: str) -> RateLimitSnapshot:
        resolved_user = self.resolve_user_id(user_id)
        usage = self._store.get_usage(resolved_user)
        return RateLimitSnapshot(
            user_id=resolved_user,
            day_key=self._store.day_key(),
            request_count=usage.request_count,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            daily_max_requests=self._settings.rate_limit_daily_max_requests_per_user,
            daily_max_tokens=self._settings.rate_limit_daily_max_tokens_per_user,
            daily_max_cost_usd=self._settings.rate_limit_daily_max_cost_usd_per_user,
        )

    def check_request_allowed(self, user_id: str | None) -> None:
        if not self.enabled:
            return
        resolved_user = self.resolve_user_id(user_id)
        usage = self._store.get_usage(resolved_user)
        limit = self._settings.rate_limit_daily_max_requests_per_user
        if usage.request_count >= limit:
            raise RateLimitExceededError(
                user_id=resolved_user,
                limit_type="daily_requests",
                limit_value=limit,
                current_value=usage.request_count,
            )

    def reserve_request(self, user_id: str | None) -> DailyUsage:
        if not self.enabled:
            return DailyUsage()
        resolved_user = self.resolve_user_id(user_id)
        self.check_request_allowed(resolved_user)
        return self._store.increment_requests(resolved_user)

    def check_tokens_allowed(self, user_id: str | None, *, estimated_tokens: int = 0) -> None:
        if not self.enabled:
            return
        resolved_user = self.resolve_user_id(user_id)
        usage = self._store.get_usage(resolved_user)
        token_limit = self._settings.rate_limit_daily_max_tokens_per_user
        projected_tokens = usage.total_tokens + max(estimated_tokens, 0)
        if projected_tokens > token_limit:
            raise RateLimitExceededError(
                user_id=resolved_user,
                limit_type="daily_tokens",
                limit_value=token_limit,
                current_value=projected_tokens,
            )

        cost_limit = self._settings.rate_limit_daily_max_cost_usd_per_user
        if usage.estimated_cost_usd >= cost_limit:
            raise RateLimitExceededError(
                user_id=resolved_user,
                limit_type="daily_cost_usd",
                limit_value=cost_limit,
                current_value=usage.estimated_cost_usd,
            )

    def record_usage(
        self,
        user_id: str | None,
        *,
        input_tokens: int,
        output_tokens: int,
        model_name: str,
        cached_tokens: int = 0,
    ) -> DailyUsage:
        if not self.enabled:
            return DailyUsage()
        resolved_user = self.resolve_user_id(user_id)
        cost_usd = estimate_cost_usd(
            model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )
        usage = self._store.record_tokens(
            resolved_user,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        token_limit = self._settings.rate_limit_daily_max_tokens_per_user
        if usage.total_tokens > token_limit:
            raise RateLimitExceededError(
                user_id=resolved_user,
                limit_type="daily_tokens",
                limit_value=token_limit,
                current_value=usage.total_tokens,
            )
        cost_limit = self._settings.rate_limit_daily_max_cost_usd_per_user
        if usage.estimated_cost_usd > cost_limit:
            raise RateLimitExceededError(
                user_id=resolved_user,
                limit_type="daily_cost_usd",
                limit_value=cost_limit,
                current_value=usage.estimated_cost_usd,
            )
        return usage

    def record_llm_response(
        self,
        user_id: str | None,
        response: Any,
        *,
        model_name: str,
        estimated_input_tokens: int = 0,
    ) -> None:
        input_tokens, output_tokens = extract_token_usage(
            response,
            estimated_input_tokens=estimated_input_tokens,
        )
        self.record_usage(
            user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            cached_tokens=extract_cached_tokens(response),
        )

    def check_active_user_tokens(self, *, estimated_tokens: int = 0) -> None:
        self.check_tokens_allowed(get_rate_limit_user_id(), estimated_tokens=estimated_tokens)

    def record_active_user_response(
        self,
        response: Any,
        *,
        model_name: str,
        estimated_input_tokens: int = 0,
    ) -> None:
        self.record_llm_response(
            get_rate_limit_user_id(),
            response,
            model_name=model_name,
            estimated_input_tokens=estimated_input_tokens,
        )


def estimate_message_tokens(messages: list[Any]) -> int:
    """Rough token estimate from message content length."""
    total_chars = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))
                else:
                    total_chars += len(str(block))
        else:
            total_chars += len(str(content))
    return max(total_chars // 4, 1)


def extract_token_usage(
    response: Any,
    *,
    estimated_input_tokens: int = 0,
) -> tuple[int, int]:
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    if usage_metadata:
        input_tokens = int(usage_metadata.get("input_tokens", 0) or 0)
        output_tokens = int(usage_metadata.get("output_tokens", 0) or 0)
        if input_tokens or output_tokens:
            return input_tokens, output_tokens

    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage", {})
    if token_usage:
        input_tokens = int(token_usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(token_usage.get("completion_tokens", 0) or 0)
        if input_tokens or output_tokens:
            return input_tokens, output_tokens

    if isinstance(response, BaseModel) and not hasattr(response, "content"):
        # A parsed structured-output object (e.g. the return value of
        # with_structured_output(...).invoke() without include_raw=True) carries no
        # usage metadata of its own. Silently falling through to the estimate below
        # would fabricate an input-token count and report 0 output tokens -- the
        # exact metering bug that lets structured-output calls defeat the per-user
        # daily cost/token cap. Fail loudly instead: callers must meter the raw
        # AIMessage (with_structured_output(..., include_raw=True)), not the parsed
        # object. Real LangChain messages always have `.content`, even empty, so
        # this never misfires on a genuine response.
        raise ValueError(
            "extract_token_usage received a parsed structured-output object with no "
            "usage_metadata -- pass the raw AIMessage, not the parsed object "
            "(use with_structured_output(..., include_raw=True))."
        )

    output_text = getattr(response, "content", "")
    output_tokens = max(len(str(output_text)) // 4, 0)
    return max(estimated_input_tokens, 0), output_tokens


def extract_cached_tokens(response: Any) -> int:
    """Return OpenAI/Anthropic prompt-cache read tokens from a response, if reported.

    LangChain surfaces this as `usage_metadata.input_token_details.cache_read`
    (mapped from OpenAI's `usage.prompt_tokens_details.cached_tokens`). Absent
    for providers/responses that don't report cache usage.
    """
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    input_token_details = usage_metadata.get("input_token_details") or {}
    return int(input_token_details.get("cache_read", 0) or 0)
