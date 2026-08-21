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
      nodes/                 node implementations, one module per branch
      agents/                coach and QA agents
      tools/                 tools the agents' LLM nodes may call
      verification/          deterministic gate + RAGAS gate
      runtime/
        base.py              GraphRuntime — the persistence seam (LangGraph ABCs)
        backends/            postgres.py, memory.py + the backend registry
        namespaces.py        long-term memory namespace scheme
  models/                    SQLModel ORM (Alembic owns migrations)
  schemas/                   graph state, API and domain models
  services/                  database, LLM, profile, knowledge
tests/
docker/
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

## Running everything in Docker

```bash
docker compose up --build
```

Brings up Postgres and the API together. The app container applies migrations on start
(`RUN_MIGRATIONS=true` in `docker/app.env`) and serves on the same port 8000.

Two env files are layered onto the app container: `.env.<APP_ENV>` for the real settings, then
`docker/app.env` for the few values that differ between the host and the compose network —
`POSTGRES_HOST`/`POSTGRES_PORT` point at `localhost:5433` from your machine but `db:5432` from
inside. Later files win, so neither has to be edited to run the other way.

`APP_ENV` selects the env file for both services, defaulting to `development`:

```bash
APP_ENV=staging docker compose up -d
```

The image is large — roughly 2 GB — because `llm-guard` (the `llm_guard` node, spec §1) pulls
torch and transformers, and `ragas` (the `ragas_verification` node, spec §5) pulls pandas and
pyarrow. Both are request-path dependencies in this design, so neither can move to an extra.

## Checks

```bash
uv run ruff format . && uv run ruff check --fix . && uv run pytest
```
