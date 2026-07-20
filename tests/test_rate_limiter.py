import pytest
from langchain_core.messages import AIMessage

from core.config.settings import Settings
from core.rate_limit import AIRateLimiter, InMemoryUsageStore, RateLimitExceededError
from core.rate_limit.context import reset_rate_limit_user_id, set_rate_limit_user_id
from core.rate_limit.limiter import extract_token_usage
from core.rate_limit.pricing import estimate_cost_usd
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask


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


def test_extract_token_usage_reads_real_usage_from_ai_message() -> None:
    message = AIMessage(
        content="",
        usage_metadata={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
    )
    input_tokens, output_tokens = extract_token_usage(message, estimated_input_tokens=999)
    assert (input_tokens, output_tokens) == (50, 20)


def test_extract_token_usage_rejects_parsed_structured_output_object() -> None:
    """Regression test for A4: with_structured_output(...).invoke() (without
    include_raw=True) returns the parsed Pydantic object directly, not the raw
    AIMessage. That object has no usage_metadata, so silently falling through to the
    generic estimate would fabricate an input-token count and report 0 output tokens --
    the exact bug that let structured-output calls defeat the per-user daily cost/token
    cap. extract_token_usage must fail loudly on this shape instead of silently zeroing
    out output tokens."""
    parsed = ExecutionPlan(
        plan_rationale="Rationale text long enough to satisfy schema validation.",
        tasks=[
            PlanTask(order=1, task="Research topic one", rationale="Rationale long enough here"),
            PlanTask(order=2, task="Research topic two", rationale="Rationale long enough here"),
            PlanTask(order=3, task="Research topic three", rationale="Rationale long enough here"),
        ],
        plan_markdown="# Plan\n\nEnough characters to satisfy schema validation.\n",
    )
    with pytest.raises(ValueError, match="usage_metadata"):
        extract_token_usage(parsed, estimated_input_tokens=500)
