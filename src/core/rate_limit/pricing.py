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
