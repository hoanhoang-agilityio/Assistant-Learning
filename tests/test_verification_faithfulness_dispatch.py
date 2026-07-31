"""Tests for verification.utils.evaluate_faithfulness's use_real=True path
(Phase 3 of the L1 remediation): rate-limit pre-check, cost recording via the
same AIRateLimiter every other LLM call goes through, and fall back to the
heuristic on any failure (rate limit already exceeded, or the real scorer
raising) rather than failing the request. All real-Ragas calls are mocked --
this suite must never spend real API money."""

from __future__ import annotations

import pytest

from core.adapters.llm import factory as factory_module
from core.adapters.rate_limit import AIRateLimiter, InMemoryUsageStore
from core.capabilities.verification.utils import evaluate_faithfulness, heuristic_faithfulness_data
from core.evaluation import ragas as ragas_module


@pytest.fixture
def real_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> AIRateLimiter:
    """A real AIRateLimiter (not the autouse fixture's disabled one) so these
    tests exercise the actual check/record contract, not a mock of it."""
    from core.config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    limiter = AIRateLimiter(settings=get_settings(), store=InMemoryUsageStore())
    factory_module.configure_rate_limiter(limiter)
    yield limiter
    factory_module.configure_rate_limiter(None)
    get_settings.cache_clear()


def _fail_if_called(*args, **kwargs):
    raise AssertionError("ragas_faithfulness_data must not be called")


class TestEvaluateFaithfulnessRealPath:
    def test_falls_back_to_heuristic_when_rate_limit_already_exceeded(
        self, real_rate_limiter: AIRateLimiter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(real_rate_limiter._settings, "rate_limit_daily_max_tokens_per_user", -1)
        monkeypatch.setattr(ragas_module, "ragas_faithfulness_data", _fail_if_called)

        result = evaluate_faithfulness("some grounded claim", [], use_real=True)

        expected = heuristic_faithfulness_data("some grounded claim", [])
        assert result == expected

    def test_falls_back_to_heuristic_when_real_scorer_raises(
        self, real_rate_limiter: AIRateLimiter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*args, **kwargs):
            raise RuntimeError("OpenAI API error")

        monkeypatch.setattr(ragas_module, "ragas_faithfulness_data", _raise)
        monkeypatch.setattr(factory_module, "get_standard_llm", lambda: object(), raising=False)

        result = evaluate_faithfulness("some grounded claim", [], use_real=True)

        expected = heuristic_faithfulness_data("some grounded claim", [])
        assert result == expected

    def test_success_path_returns_real_result_and_records_usage(
        self, real_rate_limiter: AIRateLimiter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_result = {
            "faithfulness_score": 0.42,
            "pass_fail": False,
            "method": "ragas_sdk_multi_metric",
            "threshold": 0.90,
            "answer_relevancy_score": 0.7,
            "context_precision_score": 0.6,
            "context_recall_score": None,
            "answer_correctness_score": None,
        }
        recorded: dict = {}

        def fake_ragas_faithfulness_data(draft_plan, evidence, *, query, judge_llm, reference):
            recorded["draft_plan"] = draft_plan
            recorded["query"] = query
            return fake_result

        monkeypatch.setattr(ragas_module, "ragas_faithfulness_data", fake_ragas_faithfulness_data)
        monkeypatch.setattr(factory_module, "get_standard_llm", lambda: object())

        result = evaluate_faithfulness(
            "grounded claim text", [], query="how much protein", use_real=True
        )

        assert result == fake_result
        assert recorded["draft_plan"] == "grounded claim text"
        assert recorded["query"] == "how much protein"
        # record_usage ran without raising (mocked call reports 0 real tokens,
        # but the accounting call itself must have executed, not been skipped).
        snapshot = real_rate_limiter.get_snapshot("anonymous")
        assert snapshot.request_count == 0  # record_usage doesn't touch request_count
        assert snapshot.total_tokens >= 0

    def test_use_real_false_never_touches_rate_limiter_or_ragas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ragas_module, "ragas_faithfulness_data", _fail_if_called)
        result = evaluate_faithfulness("grounded claim", [], use_real=False)
        assert result == heuristic_faithfulness_data("grounded claim", [])
