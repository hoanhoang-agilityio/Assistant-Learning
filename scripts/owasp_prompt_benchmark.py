#!/usr/bin/env python3
"""Run OWASP system-prompt benchmarks and write JSON/CSV reports.

Suites:
  scope       — original decision-oriented probes (topic_scope / intent + markers)
  robustness  — property-based production prompt robustness (planner/edit/research/…)

Default mode inventories the fixture (no LLM). Live mode:

  uv run python scripts/owasp_prompt_benchmark.py --suite robustness --live
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from core.evaluation.owasp_prompt_benchmark import (
    load_owasp_prompt_cases,
    results_as_dicts,
    run_live_case,
    score_response,
    summarize_results,
    validate_fixture_inventory,
)
from core.evaluation.owasp_prompt_robustness import (
    ensure_default_live_runners_registered,
    list_live_runner_targets,
    load_robustness_cases,
    run_live_robustness_case,
    score_security_properties,
    summarize_robustness_results,
    validate_robustness_inventory,
)
from core.evaluation.owasp_prompt_robustness import (
    results_as_dicts as robustness_results_as_dicts,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCOPE_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "owasp_system_prompt_benchmark.json"
DEFAULT_ROBUSTNESS_FIXTURE = (
    _PROJECT_ROOT / "tests" / "fixtures" / "owasp_system_prompt_robustness.json"
)
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "var" / "workspace" / "benchmarks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OWASP LLM Top 10 system-prompt benchmark for PT AI Core."
    )
    parser.add_argument(
        "--suite",
        choices=("scope", "robustness"),
        default="scope",
        help="scope = decision probes; robustness = property-based prompt suite.",
    )
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Invoke real prompt surfaces (requires API keys; costs tokens).",
    )
    parser.add_argument(
        "--responses",
        type=Path,
        default=None,
        help="Optional JSON map {case_id: response_text} for offline scoring.",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all cases.")
    parser.add_argument(
        "--target",
        type=str,
        default="",
        help="Optional filter by target_prompt.",
    )
    return parser.parse_args()


def write_reports(output_dir: Path, payload: dict, *, prefix: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{prefix}_{timestamp}.json"
    csv_path = output_dir / f"{prefix}_{timestamp}.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rows = payload.get("results", [])
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["case_id"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {
                key: (json.dumps(value) if isinstance(value, (list, dict, tuple)) else value)
                for key, value in row.items()
            }
            writer.writerow(flat)
    return json_path, csv_path


def run_scope_suite(args: argparse.Namespace) -> int:
    fixture = args.fixture or DEFAULT_SCOPE_FIXTURE
    cases = load_owasp_prompt_cases(fixture)
    if args.target:
        cases = [case for case in cases if case.target_prompt == args.target]
    if args.limit > 0:
        cases = cases[: args.limit]
    inventory = validate_fixture_inventory(cases)
    if args.live:
        results = [run_live_case(case) for case in cases]
    elif args.responses is not None:
        responses = json.loads(args.responses.read_text(encoding="utf-8"))
        results = [score_response(case, responses.get(case.case_id, "")) for case in cases]
    else:
        payload = {
            "mode": "inventory",
            "suite": "scope",
            "inventory": inventory,
            "cases": [
                {
                    "id": case.case_id,
                    "owasp_id": case.owasp_id,
                    "target_prompt": case.target_prompt,
                    "severity": case.severity,
                    "attack_type": case.attack_type,
                }
                for case in cases
            ],
            "results": [],
        }
        json_path, csv_path = write_reports(
            args.output_dir, payload, prefix="owasp_prompt_benchmark"
        )
        print(f"[scope] Inventory: {inventory['case_count']} cases")
        print(f"By OWASP: {inventory['by_owasp_id']}")
        print(f"By target: {inventory['by_target_prompt']}")
        print(f"Wrote {json_path}")
        print(f"Wrote {csv_path}")
        return 0

    summary = summarize_results(results)
    payload = {
        "mode": "live" if args.live else "offline_responses",
        "suite": "scope",
        "inventory": inventory,
        "summary": summary,
        "results": results_as_dicts(results),
    }
    json_path, csv_path = write_reports(args.output_dir, payload, prefix="owasp_prompt_benchmark")
    print(
        f"[scope] pass={summary['pass']} fail={summary['fail']} "
        f"inconclusive={summary['inconclusive']} / {summary['total']}"
    )
    if summary["failed_case_ids"]:
        print(f"Failed: {', '.join(summary['failed_case_ids'])}")
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 1 if summary["fail"] else 0


def run_robustness_suite(args: argparse.Namespace) -> int:
    fixture = args.fixture or DEFAULT_ROBUSTNESS_FIXTURE
    cases = load_robustness_cases(fixture)
    if args.target:
        cases = [case for case in cases if case.target_prompt == args.target]
    if args.limit > 0:
        cases = cases[: args.limit]
    inventory = validate_robustness_inventory(cases)
    ensure_default_live_runners_registered()

    if args.live:
        results = [run_live_robustness_case(case) for case in cases]
    elif args.responses is not None:
        responses = json.loads(args.responses.read_text(encoding="utf-8"))
        results = [
            score_security_properties(case, responses.get(case.case_id, "")) for case in cases
        ]
    else:
        payload = {
            "mode": "inventory",
            "suite": "robustness",
            "inventory": inventory,
            "registered_live_runners": list_live_runner_targets(),
            "cases": [
                {
                    "id": case.case_id,
                    "owasp_id": case.owasp_id,
                    "target_prompt": case.target_prompt,
                    "attack_family": case.attack_family,
                    "severity": case.severity,
                    "objective": case.objective,
                    "expected_security_properties": list(case.expected_security_properties),
                }
                for case in cases
            ],
            "results": [],
        }
        json_path, csv_path = write_reports(
            args.output_dir, payload, prefix="owasp_prompt_robustness"
        )
        print(f"[robustness] Inventory: {inventory['case_count']} cases")
        print(f"By OWASP: {inventory['by_owasp_id']}")
        print(f"By target: {inventory['by_target_prompt']}")
        print(f"By family: {inventory['by_attack_family']}")
        print(f"Live runners: {list_live_runner_targets()}")
        print(f"Wrote {json_path}")
        print(f"Wrote {csv_path}")
        return 0

    summary = summarize_robustness_results(results)
    payload = {
        "mode": "live" if args.live else "offline_responses",
        "suite": "robustness",
        "inventory": inventory,
        "registered_live_runners": list_live_runner_targets(),
        "summary": summary,
        "results": robustness_results_as_dicts(results),
    }
    json_path, csv_path = write_reports(args.output_dir, payload, prefix="owasp_prompt_robustness")
    print(
        f"[robustness] pass={summary['pass']} fail={summary['fail']} "
        f"inconclusive={summary['inconclusive']} / {summary['total']}"
    )
    if summary["failed_case_ids"]:
        print(f"Failed: {', '.join(summary['failed_case_ids'])}")
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 1 if summary["fail"] else 0


def main() -> int:
    args = parse_args()
    if args.suite == "robustness":
        return run_robustness_suite(args)
    return run_scope_suite(args)


if __name__ == "__main__":
    raise SystemExit(main())
