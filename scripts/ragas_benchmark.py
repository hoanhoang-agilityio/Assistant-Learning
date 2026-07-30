#!/usr/bin/env python3
"""Batch faithfulness benchmark over golden fitness queries."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from core.evaluation.ragas_benchmark import (  # noqa: E402
    load_golden_cases,
    run_golden_case,
    summarize_results,
)

DEFAULT_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "ragas_golden.json"
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "var" / "workspace" / "benchmarks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run faithfulness benchmark on golden queries.")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to golden cases JSON fixture.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for JSON and CSV reports.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on number of cases (0 = all).",
    )
    return parser.parse_args()


def write_reports(output_dir: Path, payload: dict) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"ragas_benchmark_{timestamp}.json"
    csv_path = output_dir / f"ragas_benchmark_{timestamp}.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "faithfulness_score",
                "pass_fail",
                "min_faithfulness",
                "workspace_path",
            ],
        )
        writer.writeheader()
        for row in payload["results"]:
            writer.writerow(row)
    return json_path, csv_path


def main() -> int:
    args = parse_args()
    cases = load_golden_cases(args.fixture)
    if args.limit > 0:
        cases = cases[: args.limit]

    workspace_root = args.output_dir / "runs"
    workspace_root.mkdir(parents=True, exist_ok=True)
    results = [
        run_golden_case(case, workspace_root=workspace_root, run_id=f"bench-{case.case_id}")
        for case in cases
    ]
    summary = summarize_results(results)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture": str(args.fixture),
        "summary": summary,
        "results": [
            {
                "case_id": result.case_id,
                "faithfulness_score": result.faithfulness_score,
                "pass_fail": result.pass_fail,
                "min_faithfulness": result.min_faithfulness,
                "workspace_path": result.workspace_path,
            }
            for result in results
        ],
    }
    json_path, csv_path = write_reports(args.output_dir, payload)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
