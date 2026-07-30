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

> Without a reachable Postgres the test suite does not fail — it **hangs** on connection
> pool timeouts. If `uv run pytest` appears stuck, check the container first.

One-time schema setup for the Fitness Knowledge Store (idempotent, safe to re-run):

```bash
uv run python scripts/bootstrap_fitness_db.py
uv run python scripts/ingest_knowledge.py   # loads the checked-in guideline corpus
```

### Optional extras

| Extra | Install | What it adds |
|---|---|---|
| `dev` | `uv sync --extra dev` | pytest, ruff, pre-commit |
| `eval` | `uv sync --extra eval` | the Ragas SDK — **not** a runtime dependency |

`ragas` is deliberately outside the runtime dependencies: it pulls in ~340 MB of transitive
packages and nothing imports it at module scope. Install the `eval` extra when running the
faithfulness benchmark, or when enabling `VERIFICATION_USE_REAL_RAGAS` /
`VERIFICATION_PRODUCTION_USE_REAL_RAGAS` — those flags reach the real SDK and raise
`ModuleNotFoundError` without it.

## Run tests

```bash
uv run pytest
uv run ruff check src tests scripts
```

Tests that need live credentials skip themselves when `OPENAI_API_KEY` is unset, so the
suite is green without secrets.

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
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/runs` | Create and start a run |
| `GET` | `/runs` | List runs for a user |
| `GET` | `/runs/{run_id}` | Get run status |
| `POST` | `/runs/{run_id}/resume` | Resume HITL (approve / reject / clarify) |
| `POST` | `/runs/{run_id}/continue` | Continue a run with a follow-up message |
| `GET` | `/runs/{run_id}/events` | Server-sent events stream of run progress |
| `GET` | `/users/{user_id}/runs` | Run history for a user |

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
uv run python -m core.adapters.mcp.fitness_server
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

## Run in Docker

```bash
docker build -t pt-ai-core .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://pt_ai:pt_ai_dev@host.docker.internal:5433/pt_ai_core" \
  -e OPENAI_API_KEY=... -e TAVILY_API_KEY=... \
  -v pt-ai-workspace:/var/lib/pt-ai/workspace \
  pt-ai-core
```

Multi-stage build, runs as a non-root user, healthchecked on `/health`, and writes run
artifacts to a volume rather than into the source tree. Built **without** the `eval` extra;
pass `--build-arg EXTRAS="--extra eval"` if you need the real-Ragas paths.

## Configuration

All settings come from environment variables (see `.env.example` for the full list).

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | **Takes precedence over every `POSTGRES_*` variable.** Setting `POSTGRES_HOST`/`POSTGRES_PORT` has no effect while this is set. |
| `WORKSPACE_ROOT` | `./var/workspace` | Run artifacts. Relative paths resolve against the project root. Never point this inside `src/`. |
| `LOG_LEVEL` | `INFO` | Applied at API startup. |
| `LOG_FORMAT` | `json` | `json` for machine-parseable production logs, `text` for readable local output. Records carry `run_id`/`thread_id` correlation ids. |
| `MOCK_RESEARCH` | `false` | Skip live Tavily calls. |
| `MOCK_FITNESS_KB` | `false` | Skip the Fitness MCP Server. |

## Faithfulness benchmark

```bash
uv sync --extra eval          # required: the benchmark can use the real Ragas SDK
uv run python scripts/ragas_benchmark.py
```

Reports are written to `var/workspace/benchmarks/`.

For evaluation workflow details (golden dataset, integration tests, optional Ragas SDK smoke test), see `src/docs/ragas-evaluation.md`.

LangFuse Runs → Traces → Threads (Sessions) mapping: `src/docs/langfuse-trace-checklist.md`.

## OWASP system-prompt benchmark

Two suites mapped to [OWASP LLM Top 10 2025](https://owasp.org/www-project-top-10-for-large-language-model-applications/):

1. **scope** — decision-oriented probes (`topic_scope_judge` / `intent_judge`)
2. **robustness** — property-based probes against production prompts (planner, edit, research, rewriter, router)

```bash
# Inventory (no LLM)
uv run python scripts/owasp_prompt_benchmark.py --suite scope
uv run python scripts/owasp_prompt_benchmark.py --suite robustness
uv run pytest tests/test_owasp_prompt_benchmark.py tests/test_owasp_prompt_robustness.py -v

# Live (costs tokens)
uv run python scripts/owasp_prompt_benchmark.py --suite scope --live
uv run python scripts/owasp_prompt_benchmark.py --suite robustness --live --target fitness_planner
```

Fixtures:
- `tests/fixtures/owasp_system_prompt_benchmark.json`
- `tests/fixtures/owasp_system_prompt_robustness.json`

Report + fix plan: `docs/reports/owasp_system_prompt_benchmark_live_report_and_fix_plan_2026-07-29.md`.

## Project layout

```text
src/
├── api/            # FastAPI app — routes, DI wiring, schemas
├── ui/             # Streamlit client (HTTP-only; imports nothing from core)
├── core/
│   ├── capabilities/    # the business capabilities the supervisor routes between
│   │                    #   fitness  planning  research  user  verification
│   ├── orchestration/   # LangGraph wiring and run execution
│   │                    #   graph  agents  routing  hitl  persist  state.py
│   ├── shared/          # cross-capability kernels, owned by no single capability
│   │                    #   profile  grounding  knowledge  planning  execution_context
│   ├── adapters/        # everything wrapping an external system
│   │                    #   llm  mcp  db  observability  rate_limit  vfs
│   ├── config/          # Settings
│   └── evaluation/      # Ragas + OWASP benchmarks, shadow eval
└── docs/           # Implementation specs and checklists
tests/
scripts/
var/workspace/      # runtime artifacts (gitignored, never inside src/)
```

What the grouping does and does not tell you:

- **A module belongs in `shared/` when more than one capability reads it.** `profile`,
  `knowledge` and the `ExecutionPlan` kernel are there because their consumers were counted,
  not because of how they looked. Anything a single capability owns lives inside that
  capability.
- **`adapters/` marks the modules that talk to something outside this process** — LLM
  providers, MCP transports, Postgres, Langfuse, the filesystem.
- **It is not yet a dependency rule.** `capabilities/` currently imports `adapters/`
  directly in ~28 places (mostly `vfs` and `llm`) and `shared/` in ~14. Making external
  systems arrive only as injected collaborators is a separate, unfinished piece of work —
  the grouping makes those imports visible, it does not prevent them.

## CI

`.gitlab-ci.yml` runs four jobs: `lint` (ruff), `test` (pytest against a pgvector service),
`build` (wheel, asserting it ships `core`/`api`/`ui`), and `runtime-deps` — which installs
without the dev and eval extras and imports the app, catching "works in dev, cannot start in
production" dependency gaps.
