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
    auth.py                  register/login/refresh/logout + session scoping
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
  services/                  database, auth, LLM, guard, profile, knowledge
  utils/                     JWT helpers, input sanitization
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

## Authentication

Two JWT scopes plus one opaque refresh credential. They are deliberately not
interchangeable — a leaked session token can reach exactly one conversation, and cannot
enumerate the user's other sessions or mint new ones.

| Credential | `sub` | `typ` | Grants | Lifetime |
|---|---|---|---|---|
| User token | user id | `user` | create/list/rename/delete sessions, logout | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (60) |
| Session token | session id | `session` | one session — and the graph thread behind it | same |
| Refresh token | — (opaque, hashed at rest) | — | mint a new user token | `REFRESH_TOKEN_EXPIRE_DAYS` (30) |

```
POST   /api/v1/auth/register            -> 201 {id, email, username, token, refresh_token}
POST   /api/v1/auth/login               -> 200 {access_token, refresh_token, expires_at}   (form)
POST   /api/v1/auth/refresh             -> 200 rotated pair                                (form)
POST   /api/v1/auth/logout              -> 204 denylists the jti, revokes refresh tokens
POST   /api/v1/auth/session             -> 201 {session_id, name, token}     (user token)
GET    /api/v1/auth/sessions            -> 200 [...]                         (user token)
PATCH  /api/v1/auth/session/{id}/name   -> 200                               (session token)
DELETE /api/v1/auth/session/{id}        -> 204                               (session token)
```

Conversation endpoints depend on `get_current_session`, never `get_current_user`: the
session id is the graph's `thread_id`, so that dependency is what decides who may resume a
checkpointed run.

`JWT_SECRET_KEY` is required and must be at least 32 characters — the app refuses to start
without it. Generate one per environment:

```bash
openssl rand -hex 32
```

Known trade-offs, none of them hidden: the denylist costs one indexed read per
authenticated request; `AuthService.purge_expired_tokens` exists but nothing schedules it
yet, so `revoked_token` and `refresh_token` grow until it is wired to a periodic task; HS256
uses a single shared secret, which is fine for one service but wants RS256 the moment a
second service has to verify these tokens; and replaying a rotated refresh token is
rejected without treating the whole token family as breached.

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
