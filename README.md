# PT AI Core Deep Researcher

Supervisor-orchestrated LangGraph system for **training plans** and **macro coaching**. Phase 1 includes planning, Tavily MCP research, fitness synthesis, verification, HITL approval, persistence, LangFuse tracing, and a faithfulness benchmark.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended)
- PostgreSQL with pgvector (optional for the checkpointer — in-memory checkpointer used
  by default in API tests/dev; required for the Fitness MCP Server unless
  `MOCK_FITNESS_KB=true`)
- Tavily API key for live research
- OpenAI API key (also used to embed the Fitness Knowledge Store's guideline documents)
- LangFuse (optional — local Docker at `http://localhost:3000`)

## Setup

```bash
cp .env.example .env
# Fill in TAVILY_API_KEY, OPENAI_API_KEY, and optional LANGFUSE_* / LLM keys

uv sync --extra dev
```

Start Postgres (pgvector-enabled image; optional for the checkpointer, required for the
Fitness Knowledge Store unless `MOCK_FITNESS_KB=true`):

```bash
docker compose up -d postgres
```

One-time schema setup for the Fitness Knowledge Store (idempotent, safe to re-run):

```bash
uv run python scripts/bootstrap_fitness_db.py
uv run python scripts/ingest_knowledge.py   # loads the checked-in guideline corpus
```

## Run tests

```bash
uv run pytest
uv run ruff check src tests scripts
```

## Precheck (before commit)

Install git hooks once after `uv sync --extra dev`:

```bash
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

On each commit, **precheck** runs Ruff lint/format on staged Python files. The **commit prefix** hook requires conventional messages such as `feat: ...` or `fix: ...` (merge commits are allowed).

Run manually:

```bash
uv run pre-commit run precheck --all-files
```

## Run the API

```bash
uv run uvicorn api.main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/runs` | Create and start a run |
| `GET` | `/runs/{run_id}` | Get run status |
| `POST` | `/runs/{run_id}/resume` | Resume HITL (approve / reject / clarify) |

Example:

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "query": "I want a 4-day training plan to lose weight.",
    "user_profile": {
      "age": 30, "sex": "male", "height_cm": 175,
      "current_weight_kg": 85, "target_weight_kg": 75,
      "activity_level": "gym_3x_week", "goal": "fat_loss"
    },
    "constraints": {"days_per_week": 4, "equipment": "gym"}
  }'
```

## Run the Fitness MCP Server

In a separate terminal, before starting the API (or the API degrades gracefully --
Tavily-only research, no template caching -- until this comes up):

```bash
uv run python -m core.mcp.fitness_server
```

Sole owner of guideline documents and workout templates, backed by Postgres + pgvector.
The main API connects to it once at startup via `langchain-mcp-adapters`. Set
`MOCK_FITNESS_KB=true` to skip this process entirely and use an in-memory dev double.

## Run the Streamlit UI

In a second terminal (API must be running):

```bash
export API_BASE_URL=http://localhost:8000
uv run streamlit run src/ui/app.py --server.port 8501
```

The UI lets you submit a query, poll run status, approve/reject at HITL, and view the final plan.

## Faithfulness benchmark

```bash
uv run python scripts/ragas_benchmark.py
```

Reports are written to `src/workspace/benchmarks/`.

For evaluation workflow details (golden dataset, integration tests, optional Ragas SDK smoke test), see `src/docs/ragas-evaluation.md`.

## Project layout

```text
src/
├── api/           # FastAPI app
├── core/          # Graph, subgraphs, VFS, observability
├── ui/            # Streamlit client
└── docs/          # Implementation specs and checklists
tests/
scripts/
```

## Acceptance

See [src/docs/acceptance-checklist.md](src/docs/acceptance-checklist.md) for Phase 1 completion criteria.
