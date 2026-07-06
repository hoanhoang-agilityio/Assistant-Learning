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

## Optional: “real Ragas” metric smoke test

The benchmark script in this repo currently uses the same faithfulness scoring function as production verification. If you want to directly smoke-test the Ragas SDK, you can run a minimal `faithfulness` evaluation.

Prereqs:

- Configure your model provider env (e.g. `OPENAI_API_KEY` if using OpenAI).
- Ensure `import ragas` works in your environment.

```bash
uv run python - <<'PY'
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness

dataset = Dataset.from_dict(
    {
        "question": ["What is 2+2?"],
        "answer": ["2+2 equals 4."],
        "contexts": [["A basic arithmetic fact: 2 + 2 = 4."]],
    }
)

result = evaluate(dataset, metrics=[faithfulness])
print(result)
PY
```

If this prints a result table with a `faithfulness` score, the Ragas SDK is working.

