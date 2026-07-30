import json
from pathlib import Path

import pytest

from core.evaluation import shadow_eval
from core.evaluation.shadow_eval import (
    InMemoryShadowEvalStore,
    ShadowEvalResult,
    run_shadow_evaluation_batch,
    score_run_for_shadow_eval,
)
from core.orchestration.graph.run_history_store import InMemoryRunHistoryStore
from core.vfs.bootstrap import init_run_workspace
from core.vfs.vfs import VFS


def _seed_run_workspace(
    workspace_root: Path,
    run_id: str,
    *,
    grounded_claims: str = "",
    evidence: list | None = None,
    draft_plan: str = "",
) -> None:
    run_path = init_run_workspace(run_id, workspace_root=workspace_root)
    vfs = VFS.for_run(run_path)
    if grounded_claims:
        vfs.write("fitness/grounded_claims.md", grounded_claims)
    if draft_plan:
        vfs.write("fitness/final_plan.md", draft_plan)
    vfs.write(
        "research/findings.json",
        json.dumps({"evidence": evidence or []}),
    )


def _make_run(run_id: str, *, query: str = "some query"):
    from datetime import UTC, datetime

    from core.orchestration.graph.run_history_store import RunSummary

    return RunSummary(
        run_id=run_id,
        user_id="u1",
        query=query,
        status="completed",
        steps=(),
        updated_at=datetime.now(tz=UTC),
    )


class TestInMemoryShadowEvalStore:
    def test_filter_unscored_excludes_recorded_runs(self) -> None:
        store = InMemoryShadowEvalStore()
        store.record(
            ShadowEvalResult(
                run_id="run_a",
                faithfulness_score=1.0,
                pass_fail=True,
                answer_relevancy_score=None,
                context_precision_score=None,
            )
        )
        assert store.filter_unscored(["run_a", "run_b"]) == ["run_b"]

    def test_reset_clears_all_records(self) -> None:
        store = InMemoryShadowEvalStore()
        store.record(
            ShadowEvalResult(
                run_id="run_a",
                faithfulness_score=1.0,
                pass_fail=True,
                answer_relevancy_score=None,
                context_precision_score=None,
            )
        )
        store.reset()
        assert store.filter_unscored(["run_a"]) == ["run_a"]


class TestScoreRunForShadowEval:
    def test_returns_none_when_no_scoreable_content(self, tmp_path: Path) -> None:
        run = _make_run("empty_run")
        _seed_run_workspace(tmp_path, "empty_run", grounded_claims="", evidence=[])
        assert score_run_for_shadow_eval(run, workspace_root=tmp_path) is None

    def test_returns_none_when_grounded_claims_missing_even_with_draft_plan_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression test: an earlier version fell back to scoring the full
        draft_plan (workout/macros included) when grounded_claims.md was
        missing, silently mismeasuring 5 of 6 real historical runs found
        during 2026-07-30 real-dev validation. Must skip (None), matching
        verification/executor.py's own `grounded_claims or ""` convention --
        never fall back to draft_plan."""
        run = _make_run("no_grounded_claims_run")
        _seed_run_workspace(
            tmp_path,
            "no_grounded_claims_run",
            grounded_claims="",
            draft_plan="## Training Plan\n\nBarbell bench press: 4 x 5-8",
            evidence=[{"url": "https://example.edu/x", "content": "some evidence"}],
        )

        def fail_if_called(*args, **kwargs):
            raise AssertionError(
                "evaluate_faithfulness must not be called when grounded_claims is missing"
            )

        monkeypatch.setattr(shadow_eval, "evaluate_faithfulness", fail_if_called)

        assert score_run_for_shadow_eval(run, workspace_root=tmp_path) is None

    def test_scores_via_evaluate_faithfulness_with_use_real_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _make_run("scored_run", query="how much protein")
        _seed_run_workspace(
            tmp_path,
            "scored_run",
            grounded_claims="- Protein intake near 1.6-2.2 g/kg/day. (kf_0)",
            evidence=[{"url": "https://example.edu/x", "content": "protein guidance"}],
        )

        captured: dict = {}

        def fake_evaluate_faithfulness(draft_plan, evidence, *, query="", reference=None, use_real):
            captured["draft_plan"] = draft_plan
            captured["evidence"] = evidence
            captured["query"] = query
            captured["use_real"] = use_real
            return {
                "faithfulness_score": 0.42,
                "pass_fail": False,
                "answer_relevancy_score": 0.7,
                "context_precision_score": 0.6,
            }

        monkeypatch.setattr(shadow_eval, "evaluate_faithfulness", fake_evaluate_faithfulness)

        result = score_run_for_shadow_eval(run, workspace_root=tmp_path)

        assert result == ShadowEvalResult(
            run_id="scored_run",
            faithfulness_score=0.42,
            pass_fail=False,
            answer_relevancy_score=0.7,
            context_precision_score=0.6,
        )
        # The whole point of shadow eval is the real SDK path, never the heuristic.
        assert captured["use_real"] is True
        assert captured["query"] == "how much protein"
        assert "Protein intake" in captured["draft_plan"]


class TestRunShadowEvaluationBatch:
    def _settings(self, **overrides):
        from core.config.settings import get_settings

        settings = get_settings()
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_scores_only_unscored_completed_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        history_store = InMemoryRunHistoryStore()
        history_store.upsert(run_id="r1", user_id="u", query="q1", status="completed", steps=[])
        history_store.upsert(run_id="r2", user_id="u", query="q2", status="running", steps=[])
        shadow_store = InMemoryShadowEvalStore()

        scored_run_ids: list[str] = []

        def fake_score(run, *, workspace_root=None):
            scored_run_ids.append(run.run_id)
            return ShadowEvalResult(
                run_id=run.run_id,
                faithfulness_score=1.0,
                pass_fail=True,
                answer_relevancy_score=None,
                context_precision_score=None,
            )

        monkeypatch.setattr(shadow_eval, "score_run_for_shadow_eval", fake_score)
        monkeypatch.setattr(shadow_eval, "_push_to_langfuse", lambda *a, **k: None)

        settings = self._settings(
            verification_shadow_eval_sample_rate=1.0, verification_shadow_eval_batch_size=20
        )
        scored_count = run_shadow_evaluation_batch(
            history_store=history_store, shadow_store=shadow_store, settings=settings
        )

        assert scored_count == 1
        assert scored_run_ids == ["r1"]  # r2 is "running", not eligible

        # Second sweep: r1 is already scored, must not be scored again.
        scored_run_ids.clear()
        scored_count_2 = run_shadow_evaluation_batch(
            history_store=history_store, shadow_store=shadow_store, settings=settings
        )
        assert scored_count_2 == 0
        assert scored_run_ids == []

    def test_zero_sample_rate_scores_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history_store = InMemoryRunHistoryStore()
        history_store.upsert(run_id="r1", user_id="u", query="q1", status="completed", steps=[])
        shadow_store = InMemoryShadowEvalStore()

        called = False

        def fake_score(run, *, workspace_root=None):
            nonlocal called
            called = True
            raise AssertionError("should not be called at sample_rate=0.0")

        monkeypatch.setattr(shadow_eval, "score_run_for_shadow_eval", fake_score)
        settings = self._settings(
            verification_shadow_eval_sample_rate=0.0, verification_shadow_eval_batch_size=20
        )

        scored_count = run_shadow_evaluation_batch(
            history_store=history_store, shadow_store=shadow_store, settings=settings
        )
        assert scored_count == 0
        assert called is False

    def test_one_failing_run_does_not_stop_the_rest_of_the_batch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        history_store = InMemoryRunHistoryStore()
        history_store.upsert(run_id="bad", user_id="u", query="q", status="completed", steps=[])
        history_store.upsert(run_id="good", user_id="u", query="q", status="completed", steps=[])
        shadow_store = InMemoryShadowEvalStore()

        def fake_score(run, *, workspace_root=None):
            if run.run_id == "bad":
                raise RuntimeError("boom")
            return ShadowEvalResult(
                run_id=run.run_id,
                faithfulness_score=1.0,
                pass_fail=True,
                answer_relevancy_score=None,
                context_precision_score=None,
            )

        monkeypatch.setattr(shadow_eval, "score_run_for_shadow_eval", fake_score)
        monkeypatch.setattr(shadow_eval, "_push_to_langfuse", lambda *a, **k: None)
        settings = self._settings(
            verification_shadow_eval_sample_rate=1.0, verification_shadow_eval_batch_size=20
        )

        scored_count = run_shadow_evaluation_batch(
            history_store=history_store, shadow_store=shadow_store, settings=settings
        )
        assert scored_count == 1
        assert shadow_store.filter_unscored(["good"]) == []
        assert shadow_store.filter_unscored(["bad"]) == ["bad"]
