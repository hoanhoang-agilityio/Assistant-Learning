"""Local, approximate USD cost estimation.

Two real consumers, kept separate: core.rate_limit.limiter uses this to
enforce rate_limit_daily_max_cost_usd_per_user (functional — must stay in
sync with whatever model is actually configured, or the cap silently stops
meaning what its name says); core.llm.metrics uses it for the
token_cost.log/.md pipeline report, which is a local sanity check, not an
authoritative bill — see that module's docstring. Note this does not apply
the cheaper cached-token rate (estimate_cost_usd charges input_tokens at the
full base rate regardless of how many were cache reads); Langfuse's own cost
tracking does account for that split correctly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """USD cost per one million tokens."""

    input_per_million: float
    output_per_million: float


MODEL_PRICING_USD: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(input_per_million=0.15, output_per_million=0.60),
    "gpt-4o": ModelPricing(input_per_million=2.50, output_per_million=10.00),
    "gpt-5.4-mini": ModelPricing(input_per_million=0.75, output_per_million=4.50),
    "gpt-5.4": ModelPricing(input_per_million=2.50, output_per_million=15.00),
    "claude-3-5-haiku-20241022": ModelPricing(input_per_million=0.80, output_per_million=4.00),
    "claude-sonnet-4-20250514": ModelPricing(input_per_million=3.00, output_per_million=15.00),
}

DEFAULT_MODEL_PRICING = ModelPricing(input_per_million=2.50, output_per_million=10.00)


def resolve_model_pricing(model_name: str) -> ModelPricing:
    return MODEL_PRICING_USD.get(model_name, DEFAULT_MODEL_PRICING)


def estimate_cost_usd(model_name: str, *, input_tokens: int, output_tokens: int) -> float:
    pricing = resolve_model_pricing(model_name)
    input_cost = (input_tokens / 1_000_000) * pricing.input_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_million
    return round(input_cost + output_cost, 8)
