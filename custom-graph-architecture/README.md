# Custom graph architecture

Fitness coaching and knowledge QA assistant built as a **single custom LangGraph state graph**:
an input guard, an intent classifier, a coaching branch with a deterministic verification gate and
a human-in-the-loop approval gate, and a QA branch with pgvector RAG and RAGAS faithfulness scoring.

- Design spec: [`docs/implementation-plan.md`](docs/implementation-plan.md)
- Task breakdown and progress: [`docs/estimation.md`](docs/estimation.md)
- Graph state: [`docs/state-design.md`](docs/state-design.md)
- Domain models: [`docs/data-models.md`](docs/data-models.md)

Code conventions come from the `langgraph-agent-arch` skill; the design spec says *what* to build,
the skill says *how*.

## Layout

```
src/
  main.py                    FastAPI entrypoint + lifespan
  api/v1/                    thin routes — log, delegate, map errors
  core/
    configs/config.py        the only module that reads the environment
    logging.py limiter.py    structlog, rate limiting
    langgraph/
      graph.py               root graph + the public façade the API calls
      nodes/                 node implementations, one module per node
      agents/                coach and QA agents
      tools/                 tools the agents' LLM nodes may call
      verification/          deterministic gate + RAGAS gate
      runtime/
        base.py              GraphRuntime — the persistence seam (LangGraph ABCs)
        backends/            postgres.py, memory.py + the backend registry
        namespaces.py        long-term memory namespace scheme
  models/                    SQLModel ORM (Alembic owns migrations)
  schemas/                   graph state, API and domain models
  services/                  database, LLM, guard, profile, knowledge
tests/
docker/postgres/init/       pgvector extension, run on first container start
```

## Local setup

```bash
uv sync
```

Copy the env template and fill in your keys. Compose reads this same file, so it must exist
before the first `docker compose up`:

```bash
cp .env.example .env.development
```

Start Postgres with pgvector:

```bash
docker compose up -d db
```

Apply migrations, then run the API:

```bash
uv run alembic upgrade head
```

```bash
uv run uvicorn src.main:app --reload
```

`GET /api/v1/health` should return `{"status": "ok", ...}`.

The input guard's `prompt_injection`, `toxicity` and `ban_topics`
Set `GUARD_ENABLED=false`, or trim `GUARD_SCANNERS` to the
pure-Python checks, to skip it.

Compose runs the database only — the application itself runs on the host, via uv. `APP_ENV`
selects which env file both sides read, defaulting to `development`:

```bash
APP_ENV=staging docker compose up -d db
```

## Checks

```bash
uv run ruff format . && uv run ruff check --fix . && uv run pytest
```

Tests that need a real service are marked `integration`, so the rest run with nothing else
up:

```bash
uv run pytest -m "not integration"
```

They also skip on their own when Postgres is unreachable — the marker is there to deselect
them deliberately, not to keep the suite passing.
