import pytest

from core.config.settings import Settings
from core.rate_limit import AIRateLimiter, InMemoryUsageStore, RateLimitExceededError
from core.rate_limit.context import reset_rate_limit_user_id, set_rate_limit_user_id
from core.rate_limit.pricing import estimate_cost_usd


def _limiter(
    *,
    enabled: bool = True,
    max_requests: int = 2,
    max_tokens: int = 1000,
    max_cost: float = 1.0,
) -> AIRateLimiter:
    settings = Settings(
        rate_limit_enabled=enabled,
        rate_limit_daily_max_requests_per_user=max_requests,
        rate_limit_daily_max_tokens_per_user=max_tokens,
        rate_limit_daily_max_cost_usd_per_user=max_cost,
    )
    return AIRateLimiter(settings=settings, store=InMemoryUsageStore())


def test_reserve_request_increments_daily_counter() -> None:
    limiter = _limiter(max_requests=5)
    limiter.reserve_request("alice")
    snapshot = limiter.get_snapshot("alice")
    assert snapshot.request_count == 1


def test_request_limit_blocks_additional_runs() -> None:
    limiter = _limiter(max_requests=1)
    limiter.reserve_request("alice")
    with pytest.raises(RateLimitExceededError, match="daily_requests"):
        limiter.reserve_request("alice")


def test_token_limit_blocks_llm_usage() -> None:
    limiter = _limiter(max_tokens=100)
    token = set_rate_limit_user_id("alice")
    try:
        limiter.record_usage(
            "alice",
            input_tokens=80,
            output_tokens=10,
            model_name="gpt-4o-mini",
        )
        with pytest.raises(RateLimitExceededError, match="daily_tokens"):
            limiter.check_active_user_tokens(estimated_tokens=20)
    finally:
        reset_rate_limit_user_id(token)


def test_cost_limit_blocks_after_expensive_call() -> None:
    limiter = _limiter(max_cost=0.01, max_tokens=1_000_000)
    with pytest.raises(RateLimitExceededError, match="daily_cost_usd"):
        limiter.record_usage(
            "alice",
            input_tokens=10_000,
            output_tokens=5_000,
            model_name="gpt-4o",
        )


def test_disabled_limiter_allows_unbounded_usage() -> None:
    limiter = _limiter(enabled=False, max_requests=1)
    limiter.reserve_request("alice")
    limiter.reserve_request("alice")
    snapshot = limiter.get_snapshot("alice")
    assert snapshot.request_count == 0


def test_estimate_cost_usd_uses_model_pricing() -> None:
    cost = estimate_cost_usd("gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(0.15)
