import pytest

from core.adapters.rate_limit.pricing import MODEL_PRICING_USD, validate_model_pricing_coverage
from core.config.settings import get_settings


def test_validate_model_pricing_coverage_passes_for_current_settings() -> None:
    settings = get_settings()
    validate_model_pricing_coverage(
        {
            "openai_standard_model": settings.openai_standard_model,
            "openai_xhigh_model": settings.openai_xhigh_model,
            "anthropic_xhigh_model": settings.anthropic_xhigh_model,
        }
    )


def test_validate_model_pricing_coverage_raises_on_unpriced_model() -> None:
    with pytest.raises(ValueError, match="openai_standard_model"):
        validate_model_pricing_coverage({"openai_standard_model": "gpt-not-a-real-model"})


def test_validate_model_pricing_coverage_lists_all_missing_models() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_model_pricing_coverage(
            {"openai_standard_model": "unpriced-a", "openai_xhigh_model": "unpriced-b"}
        )
    assert "unpriced-a" in str(exc_info.value)
    assert "unpriced-b" in str(exc_info.value)


def test_all_currently_priced_models_have_cached_input_rate() -> None:
    for model_name, pricing in MODEL_PRICING_USD.items():
        assert pricing.resolved_cached_input_per_million > 0, model_name
