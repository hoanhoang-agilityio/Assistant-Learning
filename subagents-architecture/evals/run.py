"""Command-line entry point for a batch evaluation run.

    uv run python -m evals.run --scope traces --max-items 50
    uv run python -m evals.run --scope observations --max-items 25

The run loop belongs to the SDK: ``run_batched_evaluation`` owns pagination,
concurrency, retries with backoff, per-item error isolation, the resume token,
and flushing scores at the end. There is deliberately no report file here —
``BatchEvaluationResult`` carries the per-evaluator stats, and Langfuse itself
is the dashboard.
"""

import argparse
import json
import sys

from langfuse import BatchEvaluationResult

from app.core.configs.config import settings
from app.core.logging import logger
from evals.client import build_client
from evals.evaluators import DOMAIN_EVALUATORS, RAG_EVALUATORS
from evals.mappers import observation_mapper, trace_mapper

# "core,io" skips observations, scores and metrics the mappers never read.
# Excluded fields come back empty (and metrics come back as -1), so never add a
# `filter` on a field excluded here.
TRACE_FIELDS = "core,io"

# Ragas metrics are multi-call by construction, so the retrieval scope is capped
# lower by default than the judge scope.
DEFAULT_MAX_ITEMS = {"traces": 50, "observations": 25}


def build_filter(scope: str) -> str:
    """Build the Langfuse filter for a scope.

    The API takes a JSON **array** of ``{type, column, operator, value}``
    conditions. It rejects an object — ``expected array, received object`` —
    even though the SDK's own ``run_batched_evaluation`` docstring shows
    ``filter='{"tags": ["production"]}'``. Its ``_build_timestamp_filter`` is
    the honest source: it appends to a list and warns when the parsed filter is
    not one.

    Traces are scoped to this environment because ``langfuse_init`` tags every
    trace with it. That filter is not cosmetic here: this instance also carries
    traces under ``langfuse-llm-as-a-judge``, from Langfuse's own server-side
    evaluators, which would otherwise be judged as if they were app traffic.

    Observations are narrowed to ``search_knowledge`` so RAG metrics never see
    turns that retrieved nothing.

    Args:
        scope: Either ``traces`` or ``observations``.

    Returns:
        The filter as a JSON array string.
    """
    if scope == "observations":
        return json.dumps(
            [{"type": "string", "column": "name", "operator": "=", "value": "search_knowledge"}]
        )
    return json.dumps(
        [
            {
                "type": "string",
                "column": "environment",
                "operator": "=",
                "value": settings.ENVIRONMENT.value,
            }
        ]
    )


def report(result: BatchEvaluationResult) -> None:
    """Print the run outcome.

    Failure counts are pipeline health, not quality: a metric with zero
    failures and an average of 0.2 ran perfectly and found bad output. Quality
    lives in the Langfuse UI, where the score comments are.

    Args:
        result: What the batch runner returned.
    """
    print("\n" + "=" * 60)
    print(
        f"fetched={result.total_items_fetched} processed={result.total_items_processed} "
        f"failed={result.total_items_failed}"
    )
    print(
        f"scores created: {result.total_scores_created}  "
        f"evaluations failed: {result.total_evaluations_failed}"
    )
    print(f"duration: {result.duration_seconds:.1f}s  completed: {result.completed}")

    print("\nper evaluator (runs / scored / failed):")
    for stats in result.evaluator_stats:
        print(
            f"  • {stats.name}: {stats.total_runs} run, "
            f"{stats.total_scores_created} scored, {stats.failed_runs} failed"
        )

    if result.error_summary:
        print("\nerrors:")
        for error, count in result.error_summary.items():
            print(f"  • {error}: {count}")

    if not result.total_items_fetched:
        print("\nNothing fetched. Check tracing is on and that traffic exists for this filter.")

    # An abstaining evaluator is silent by design, so a metric can legitimately
    # run many times and create no scores. Only a run that scored nothing at all
    # is suspicious.
    if result.total_items_processed and not result.total_scores_created:
        print("\nItems processed but no scores created — every evaluator abstained or failed.")

    # The token has no __repr__, so printing it bare yields an object address.
    # These four fields are what BatchEvaluationResumeToken(...) is rebuilt from.
    if not result.completed and result.resume_token:
        token = result.resume_token
        print("\nIncomplete. Resume with BatchEvaluationResumeToken(")
        print(f"    scope={token.scope!r},")
        print(f"    filter={token.filter!r},")
        print(f"    last_processed_timestamp={token.last_processed_timestamp!r},")
        print(f"    last_processed_id={token.last_processed_id!r},")
        print(f"    items_processed={token.items_processed},")
        print(")")


def main() -> None:
    """Parse arguments and run one batch evaluation."""
    parser = argparse.ArgumentParser(description="Score Langfuse traffic with judge evaluators")
    parser.add_argument(
        "--scope",
        choices=("traces", "observations"),
        default="traces",
        help="traces → domain judges; observations → ragas over search_knowledge",
    )
    parser.add_argument("--max-items", type=int, default=None, help="cap items fetched")
    parser.add_argument("--max-concurrency", type=int, default=5, help="parallel items")
    parser.add_argument("--verbose", action="store_true", help="SDK progress output")
    args = parser.parse_args()

    scope = args.scope
    max_items = args.max_items or DEFAULT_MAX_ITEMS[scope]
    client = build_client()

    logger.info(
        "batch_evaluation_starting",
        scope=scope,
        max_items=max_items,
        environment=settings.ENVIRONMENT.value,
        judge_model=settings.EVALUATION_LLM,
    )

    try:
        result = client.run_batched_evaluation(
            scope=scope,
            mapper=trace_mapper if scope == "traces" else observation_mapper,
            evaluators=DOMAIN_EVALUATORS if scope == "traces" else RAG_EVALUATORS,
            filter=build_filter(scope),
            fetch_trace_fields=TRACE_FIELDS if scope == "traces" else None,
            max_items=max_items,
            max_concurrency=args.max_concurrency,
            verbose=args.verbose,
        )
    except Exception as e:
        logger.exception("batch_evaluation_failed", scope=scope)
        print(f"✗ Evaluation failed: {e}")
        sys.exit(1)

    logger.info(
        "batch_evaluation_completed",
        scope=scope,
        items_processed=result.total_items_processed,
        scores_created=result.total_scores_created,
        evaluations_failed=result.total_evaluations_failed,
    )


if __name__ == "__main__":
    main()
