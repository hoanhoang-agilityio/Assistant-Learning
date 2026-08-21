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
app/
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
      runtime/               checkpointer and long-term store
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

Copy the env template and fill in your keys:

```bash
cp .env.example .env.development
```

Start Postgres with pgvector:

```bash
docker compose up -d db
```

Run the API:

```bash
uv run uvicorn app.main:app --reload
```

`GET /api/v1/health` should return `{"status": "ok", ...}`.

## Checks

```bash
uv run ruff format . && uv run ruff check --fix . && uv run pytest
```
