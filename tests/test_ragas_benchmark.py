from pathlib import Path

import pytest

from core.capabilities.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.config.settings import get_settings
from core.evaluation.ragas_benchmark import load_golden_cases, run_golden_case, summarize_results

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "ragas_golden.json"


def test_golden_fixture_loads_cases() -> None:
    cases = load_golden_cases(FIXTURE_PATH)
    assert len(cases) >= 3
    assert all(case.min_faithfulness >= FAITHFULNESS_PASS_THRESHOLD for case in cases)


def test_golden_cases_meet_faithfulness_threshold(tmp_path: Path) -> None:
    cases = load_golden_cases(FIXTURE_PATH)
    workspace_root = tmp_path / "ragas_workspace"
    results = [
        run_golden_case(case, workspace_root=workspace_root, run_id=f"test-{case.case_id}")
        for case in cases
    ]
    summary = summarize_results(results)
    assert summary["failed_count"] == 0
    assert summary["mean_faithfulness"] >= FAITHFULNESS_PASS_THRESHOLD
    assert all(result.pass_fail for result in results)


@pytest.mark.skipif(
    not get_settings().openai_api_key,
    reason=(
        "Spawns scripts/ragas_benchmark.py as a subprocess, which runs the real "
        "Research -> Fitness -> Verification pipeline against live models. The "
        "subprocess does not inherit conftest's mock wiring, so it needs a real "
        "OPENAI_API_KEY -- same guard as tests/test_fitness_mcp_server.py."
    ),
)
def test_ragas_benchmark_script_runs(tmp_path: Path) -> None:
    import subprocess
    import sys

    output_dir = tmp_path / "benchmark_out"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ragas_benchmark.py",
            "--fixture",
            str(FIXTURE_PATH),
            "--output-dir",
            str(output_dir),
            "--limit",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report_files = list(output_dir.glob("ragas_benchmark_*.json"))
    assert report_files
