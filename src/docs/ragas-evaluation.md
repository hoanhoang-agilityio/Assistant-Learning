# RAGAS Evaluation Guide (this repo)

This project already includes a benchmark and regression tests for **faithfulness**. You do **not** need a separate `evals/` folder to get started.

## What we evaluate

- **Prompt-level**: Did a single node/subgraph produce a correct, grounded output?
- **Workflow-level**: Does the end-to-end pipeline behave correctly (gates, artifacts, HITL, persist)?
- **Agent-level**: Does the system route correctly (partial reruns) and call tools as expected?

## Where eval inputs / outputs live

- **Golden dataset**: `tests/fixtures/ragas_golden.json`
- **Benchmark script**: `scripts/ragas_benchmark.py` (uses `src/core/evaluation/ragas_benchmark.py`)
- **Benchmark outputs**: `src/workspace/benchmarks/` (JSON + CSV)

## Run the benchmark (batch eval)

```bash
uv run python scripts/ragas_benchmark.py
```

Limit to N cases:

```bash
uv run python scripts/ragas_benchmark.py --limit 1
```

## Run regression tests (CI-style)

```bash
uv run pytest -q tests/test_ragas_benchmark.py -v
```

This asserts the golden set meets the project threshold (\(\ge 0.90\)).

## Run workflow + agent evaluations

Integration tests cover gates, tool paths, reruns, and happy path:

```bash
uv run pytest -q tests/integration/ -v
```

Useful focused runs:

```bash
uv run pytest -q tests/integration/test_happy_path.py -v
uv run pytest -q tests/integration/test_partial_rerun.py -v
uv run pytest -q tests/integration/test_todos_gate.py -v
uv run pytest -q tests/integration/test_tavily_research_path.py -v
```

## Real Ragas SDK scoring

Production's `_ragas_faithfulness_node` always uses the heuristic proxy (`verification/utils.py:heuristic_faithfulness_data`) — zero cost, zero latency, deterministic. The real Ragas SDK scorer lives in `src/core/evaluation/ragas.py` (`ragas_faithfulness_data`) and is wired only into the benchmark script's `evaluate_draft_faithfulness`/`run_golden_case`, gated behind `settings.verification_use_real_ragas` (off by default). See `docs/reports/known_limitations_remediation_plan.md`, L1, for the full design.

Prereqs to run it:

- Configure your model provider env (e.g. `OPENAI_API_KEY` if using OpenAI).
- Set `VERIFICATION_USE_REAL_RAGAS=true` in your environment/`.env`.

```bash
VERIFICATION_USE_REAL_RAGAS=true uv run python scripts/ragas_benchmark.py --limit 1
```

The JSON/CSV report gains `real_faithfulness_score`/`real_pass_fail` columns alongside the heuristic's `faithfulness_score`/`pass_fail` — the real score is comparison data only; it does not change the benchmark's pass/fail verdict or exit code in this scope.

### Smoke-testing the SDK directly

If you just want to confirm `ragas.evaluate()` works in your environment without going through the benchmark script, note that Ragas 0.4.x's `faithfulness` metric expects `user_input`/`response`/`retrieved_contexts` columns (not the older `question`/`answer`/`contexts` naming):

```bash
uv run python - <<'PY'
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset
from ragas.metrics import faithfulness

dataset = EvaluationDataset.from_list(
    [
        {
            "user_input": "What is 2+2?",
            "response": "2+2 equals 4.",
            "retrieved_contexts": ["A basic arithmetic fact: 2 + 2 = 4."],
        }
    ]
)

result = evaluate(dataset, metrics=[faithfulness])
print(result)
PY
```

If this prints a result table with a `faithfulness` score, the Ragas SDK is working.

