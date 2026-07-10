"""Local, approximate USD cost estimation.

Two real consumers, kept separate: core.rate_limit.limiter uses this to
enforce rate_limit_daily_max_cost_usd_per_user (functional — must stay in
sync with whatever model is actually configured, or the cap silently stops
meaning what its name says); core.llm.metrics uses it for the
token_cost.log/.md pipeline report, which is a local sanity check, not an
authoritative bill — see that module's docstring. estimate_cost_usd bills
cached_tokens at each model's cached_input_per_million rate rather than the
full input rate — Langfuse's own cost tracking accounts for the same split
and remains the source of truth for actual per-run cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """USD cost per one million tokens."""

    input_per_million: float
    output_per_million: float
    # Cache-read rate for prompt-cache hits (OpenAI/Anthropic bill these well
    # below the base input rate). Defaults to the base input rate — i.e. no
    # assumed discount — for models without a documented cached rate below.
    cached_input_per_million: float | None = None

    @property
    def resolved_cached_input_per_million(self) -> float:
        return (
            self.cached_input_per_million
            if self.cached_input_per_million is not None
            else self.input_per_million
        )


MODEL_PRICING_USD: dict[str, ModelPricing] = {
    # gpt-4o family: OpenAI prompt caching discounts cached input ~50%.
    "gpt-4o-mini": ModelPricing(
        input_per_million=0.15, output_per_million=0.60, cached_input_per_million=0.075
    ),
    "gpt-4o": ModelPricing(
        input_per_million=2.50, output_per_million=10.00, cached_input_per_million=1.25
    ),
    # gpt-5.x family: cached input billed at ~10% of base input rate.
    "gpt-5.4-mini": ModelPricing(
        input_per_million=0.75, output_per_million=4.50, cached_input_per_million=0.075
    ),
    "gpt-5.4": ModelPricing(
        input_per_million=2.50, output_per_million=15.00, cached_input_per_million=0.25
    ),
    # Anthropic prompt caching: cache reads billed at ~10% of base input rate.
    "claude-3-5-haiku-20241022": ModelPricing(
        input_per_million=0.80, output_per_million=4.00, cached_input_per_million=0.08
    ),
    "claude-sonnet-4-20250514": ModelPricing(
        input_per_million=3.00, output_per_million=15.00, cached_input_per_million=0.30
    ),
}

DEFAULT_MODEL_PRICING = ModelPricing(input_per_million=2.50, output_per_million=10.00)


def resolve_model_pricing(model_name: str) -> ModelPricing:
    return MODEL_PRICING_USD.get(model_name, DEFAULT_MODEL_PRICING)


def validate_model_pricing_coverage(configured_models: dict[str, str]) -> None:
    """Fail loudly if a configured model has no explicit MODEL_PRICING_USD entry.

    Without this, resolve_model_pricing() silently falls back to
    DEFAULT_MODEL_PRICING (a placeholder rate) for any model-name change —
    both token_cost.md's reporting and the per-user daily cost cap
    (rate_limit.limiter.AIRateLimiter) would misreport/mis-enforce with no
    warning. Call this once at process startup with the models actually
    configured (see api/main.py's lifespan).
    """
    missing = {
        setting_name: model_name
        for setting_name, model_name in configured_models.items()
        if model_name not in MODEL_PRICING_USD
    }
    if missing:
        details = ", ".join(f"{setting}={model!r}" for setting, model in missing.items())
        raise ValueError(
            f"Missing MODEL_PRICING_USD entry for configured model(s): {details}. "
            "Add pricing before deploying, or cost reporting/enforcement will "
            "silently fall back to DEFAULT_MODEL_PRICING."
        )


def estimate_cost_usd(
    model_name: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Estimate USD cost, billing cached_tokens at the model's cache-read rate.

    cached_tokens must be a subset of input_tokens (cache reads are a
    discounted portion of the input, not additional tokens).
    """
    pricing = resolve_model_pricing(model_name)
    billed_cached_tokens = max(min(cached_tokens, input_tokens), 0)
    uncached_input_tokens = input_tokens - billed_cached_tokens
    input_cost = (uncached_input_tokens / 1_000_000) * pricing.input_per_million
    cached_cost = (billed_cached_tokens / 1_000_000) * pricing.resolved_cached_input_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_million
    return round(input_cost + cached_cost + output_cost, 8)
