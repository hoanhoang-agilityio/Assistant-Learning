"""Pull-based shadow evaluation (L1 remediation, Phase 2): periodically scores
recently-completed runs with the real Ragas SDK and logs the result to
LangFuse, without touching the synchronous request path or production's
heuristic pass/fail verdict.

Deliberately pull-based, mirroring api.main's `_run_periodic_reconciliation`
(a periodic background task, `asyncio.to_thread` for the synchronous work)
rather than a per-request fire-and-forget task: verification/executor.py's
checks run inside a synchronous LangGraph node with no per-request async task
infra today, and a pull-based sweep is easier to throttle/replay/observe than
wiring a new push path into the request lifecycle. See
docs/reports/known_limitations_remediation_plan.md, L1, Phase 2.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from psycopg_pool import ConnectionPool

from core.config.settings import Settings, get_settings
from core.observability.langfuse import create_trace_id_for_run, get_langfuse_client
from core.orchestration.graph.run_history_store import RunSummary
from core.subgraphs.verification.utils import evaluate_faithfulness, load_verification_context
from core.vfs.bootstrap import run_workspace_path

logger = logging.getLogger(__name__)

# How far back a sweep looks for completed-but-unscored runs. Not tied to
# verification_shadow_eval_interval_seconds: idempotency comes from
# filter_unscored (already-scored runs are always excluded), not from this
# window, so a generous static lookback means a backlog survives the periodic
# task being down for a while instead of aging out of a short rolling window.
_LOOKBACK = timedelta(days=7)

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS shadow_faithfulness_evals (
    run_id TEXT PRIMARY KEY,
    faithfulness_score DOUBLE PRECISION NOT NULL,
    pass_fail BOOLEAN NOT NULL,
    answer_relevancy_score DOUBLE PRECISION,
    context_precision_score DOUBLE PRECISION,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class ShadowEvalResult:
    run_id: str
    faithfulness_score: float
    pass_fail: bool
    answer_relevancy_score: float | None
    context_precision_score: float | None


class RunHistorySource(Protocol):
    def list_recent_completed(self, *, since: datetime, limit: int) -> list[RunSummary]: ...


class InMemoryShadowEvalStore:
    """Process-local shadow-eval record for tests / MemorySaver-backed dev."""

    def __init__(self) -> None:
        self._rows: dict[str, ShadowEvalResult] = {}

    def filter_unscored(self, run_ids: list[str]) -> list[str]:
        return [run_id for run_id in run_ids if run_id not in self._rows]

    def record(self, result: ShadowEvalResult) -> None:
        self._rows[result.run_id] = result

    def reset(self) -> None:
        self._rows.clear()


class ShadowEvalStore:
    """Postgres-backed durable record of which runs have been shadow-scored,
    and the scores themselves (so this doubles as history for future
    dashboarding/regression analysis, not just a scored/unscored flag)."""

    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self._pool = ConnectionPool(
            conninfo,
            min_size=min_size,
            max_size=max_size,
            timeout=connect_timeout_seconds,
            open=True,
        )
        with self._pool.connection() as conn:
            conn.execute(_TABLE_DDL)
            conn.commit()

    def filter_unscored(self, run_ids: list[str]) -> list[str]:
        if not run_ids:
            return []
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT run_id FROM shadow_faithfulness_evals WHERE run_id = ANY(%s)",
                (run_ids,),
            ).fetchall()
        already_scored = {row[0] for row in rows}
        return [run_id for run_id in run_ids if run_id not in already_scored]

    def record(self, result: ShadowEvalResult) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO shadow_faithfulness_evals
                    (run_id, faithfulness_score, pass_fail,
                     answer_relevancy_score, context_precision_score, scored_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    result.run_id,
                    result.faithfulness_score,
                    result.pass_fail,
                    result.answer_relevancy_score,
                    result.context_precision_score,
                ),
            )
            conn.commit()

    def reset(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE shadow_faithfulness_evals")
            conn.commit()

    def close(self) -> None:
        self._pool.close()


def score_run_for_shadow_eval(
    run: RunSummary, *, workspace_root: Path | None = None
) -> ShadowEvalResult | None:
    """Load a completed run's verification context and score it with the real
    Ragas SDK. Returns None when the run has no scoreable content (e.g. its
    workspace was cleaned up, it never reached a verification step, or it
    predates grounded_claims.md being written) -- callers should skip, not
    fail, on None.

    Deliberately mirrors verification/executor.py's exact convention
    (`context.get("grounded_claims") or ""`) with NO draft_plan fallback: an
    earlier version of this function fell back to the full draft_plan when
    grounded_claims.md was missing, which silently scored the whole final
    plan -- engine-authored workout/macro sections included -- against
    research evidence that was never meant to ground them, producing a
    misleadingly low score unrelated to genuine citation faithfulness (found
    2026-07-30 during real-dev validation: 5 of 6 real historical runs hit
    this exact path). Skipping (None) is honest; scoring the wrong text is not.

    `workspace_root` overrides settings.workspace_root (production omits it) --
    exists so tests can point at a tmp_path instead of monkeypatching global
    settings.
    """
    workspace_path = run_workspace_path(run.run_id, workspace_root=workspace_root)
    context = load_verification_context(str(workspace_path))
    grounded_text = context.get("grounded_claims") or ""
    if not grounded_text.strip():
        return None
    evidence = context.get("evidence") or []
    result = evaluate_faithfulness(grounded_text, evidence, query=run.query, use_real=True)
    return ShadowEvalResult(
        run_id=run.run_id,
        faithfulness_score=result["faithfulness_score"],
        pass_fail=result["pass_fail"],
        answer_relevancy_score=result.get("answer_relevancy_score"),
        context_precision_score=result.get("context_precision_score"),
    )


def _push_to_langfuse(result: ShadowEvalResult, *, settings: Settings) -> None:
    client = get_langfuse_client(settings)
    if client is None:
        return
    trace_id = create_trace_id_for_run(result.run_id, settings=settings)
    client.create_score(
        name="shadow_faithfulness",
        value=result.faithfulness_score,
        trace_id=trace_id,
        data_type="NUMERIC",
        comment=f"pass_fail={result.pass_fail}",
        metadata={
            "answer_relevancy_score": result.answer_relevancy_score,
            "context_precision_score": result.context_precision_score,
            "method": "ragas_sdk_shadow_eval",
        },
    )


def run_shadow_evaluation_batch(
    *,
    history_store: RunHistorySource,
    shadow_store: ShadowEvalStore | InMemoryShadowEvalStore,
    settings: Settings | None = None,
    workspace_root: Path | None = None,
) -> int:
    """One sweep: find eligible completed runs, sample, score, persist, log.

    Returns the number of runs actually scored. Never raises on a single run's
    failure (a bad workspace read, a judge-LLM timeout, a LangFuse hiccup) --
    one bad run must not stop the rest of the batch or the periodic task
    calling this on a timer.

    `workspace_root` overrides settings.workspace_root (production omits it) --
    exists so tests can point at a tmp_path instead of monkeypatching global
    settings.
    """
    resolved = settings or get_settings()
    since = datetime.now(tz=UTC) - _LOOKBACK
    candidates = history_store.list_recent_completed(
        since=since, limit=resolved.verification_shadow_eval_batch_size
    )
    if not candidates:
        return 0
    unscored_ids = set(shadow_store.filter_unscored([run.run_id for run in candidates]))
    sample_rate = resolved.verification_shadow_eval_sample_rate
    scored_count = 0
    for run in candidates:
        if run.run_id not in unscored_ids:
            continue
        if sample_rate < 1.0 and random.random() >= sample_rate:
            continue
        try:
            result = score_run_for_shadow_eval(run, workspace_root=workspace_root)
        except Exception:
            logger.exception("Shadow eval scoring failed for run %s", run.run_id)
            continue
        if result is None:
            continue
        shadow_store.record(result)
        try:
            _push_to_langfuse(result, settings=resolved)
        except Exception:
            logger.exception("Shadow eval LangFuse push failed for run %s", run.run_id)
        scored_count += 1
    return scored_count
