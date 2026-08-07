# PT AI Core Deep Researcher

LangGraph system for **training plans** and **macro coaching**: planning, knowledge-base
retrieval, verification, a human confirm gate, persistence, JWT auth and LangFuse tracing,
behind a FastAPI service with a Streamlit front end.

---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended)
- PostgreSQL with pgvector
- OpenAI API key (also used to embed the knowledge base)
- LangFuse (optional — local Docker at `http://localhost:3000`)

## Setup

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY, JWT_SECRET_KEY, and optional LANGFUSE_* keys

uv sync --extra dev
```

Start Postgres (pgvector-enabled image):

```bash
docker compose up -d db
```

> Without a reachable Postgres the test suite does not fail — it **hangs** on connection
> pool timeouts. If `uv run pytest` appears stuck, check the container first.

Then apply migrations and seed — see [Run the API](#run-the-api).

### Optional extras

| Extra | Install | What it adds |
|---|---|---|
| `dev` | `uv sync --extra dev` | pytest, ruff, pre-commit |

## Run tests

```bash
uv run pytest
uv run ruff check app tests scripts
```

Tests that need live credentials skip themselves when `OPENAI_API_KEY` is unset, so the
suite is green without secrets.

The `app/` auth suite runs against a throwaway SQLite file and needs no database:

```bash
uv run pytest tests/test_auth_flow.py -v
```

Two of those tests are the privilege boundary between the token scopes —
`test_session_token_cannot_create_session` and
`test_user_token_cannot_reach_session_endpoint`. A failure there is a security regression,
not a flaky test.

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

This is the entrypoint the Dockerfile uses.

```bash
docker compose up -d db          # Postgres on host port 5433
uv sync --extra dev
uv run alembic upgrade head      # creates user / session / refresh_token / revoked_token
uv run python scripts/seed_catalog.py     # exercise catalog
uv run python scripts/seed_config.py      # template library + rubrics
uv run python scripts/seed_knowledge.py   # knowledge base (needs OPENAI_API_KEY)
uv run uvicorn app.main:app --reload
```

Swagger UI: **http://localhost:8000/docs**

### Seeding the knowledge base

`search_knowledge` reads the `knowledge_chunks` table, and until that table is populated
the tool returns `[]` on every query — the QA agent then answers from the model's own
knowledge and says the base had nothing, which is honest but not the intended state.

The source of truth is `data/knowledge/*.docx`. Each `Heading 2` section becomes one
passage (long sections are split, with the heading repeated on every part), embedded with
`text-embedding-3-small` and stored as a pgvector column.

```bash
uv run python scripts/seed_knowledge.py --dry-run   # chunk plan, no API calls, no writes
uv run python scripts/seed_knowledge.py             # embed and upsert
# -> knowledge base: 88 passages — 88 inserted, 0 updated, 0 unchanged, 0 deleted
```

Idempotent and frugal: only passages whose text changed are re-embedded, and a section
deleted from a document is deleted from the table. Add a document by dropping a `.docx`
into `data/knowledge/` and re-running — no code change.

Settings come from `.env.development` (selected by `APP_ENV`, default `development`). Two
things stop the app from starting, both deliberately:

- `JWT_SECRET_KEY` shorter than 32 characters → `RuntimeError` at startup.
  Generate one with `openssl rand -hex 32`.
- `ALLOWED_ORIGINS` containing `*` → `RuntimeError` at import. A wildcard origin combined
  with `allow_credentials=True` is rejected by browsers and is a real credential-leak path
  if someone later "fixes" it by reflecting the request origin.

To skip Postgres entirely while poking at Swagger, uncomment in `.env.development`:

```
AUTH_DATABASE_URL=sqlite:///./auth_dev.db
```

### Authentication

Two JWT scopes plus one opaque refresh credential. They are **not** interchangeable.

| Credential | `typ` | `sub` | Grants | Lifetime |
|---|---|---|---|---|
| User token | `user` | user id | create/list/rename/delete sessions, logout | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (60) |
| Session token | `session` | session id | one session only — what conversation endpoints depend on | same |
| Refresh token | — | — | mint a new user token; single-use, rotates on every call | `REFRESH_TOKEN_EXPIRE_DAYS` (30) |

| Method | Path | Guard |
|--------|------|-------|
| `POST` | `/api/v1/auth/register` | public, 10/hour |
| `POST` | `/api/v1/auth/login` | public, 20/min |
| `POST` | `/api/v1/auth/refresh` | public, 30/hour — needs a valid refresh token |
| `POST` | `/api/v1/auth/logout` | user token |
| `POST` | `/api/v1/auth/session` | user token |
| `GET` | `/api/v1/auth/sessions` | user token |
| `PATCH` | `/api/v1/auth/session/{session_id}/name` | session token |
| `DELETE` | `/api/v1/auth/session/{session_id}` | session token |
| `GET` | `/`, `/health`, `/api/v1/health` | public |

Guarding a new route is one dependency. Take the id from the returned object, **never** from
the path or body — a route that reads a user id straight from the URL is an authorization
hole, not a shortcut:

```python
from app.api.v1.auth import get_current_session, get_current_user

@router.post("/chat")                       # conversation scope
async def chat(session: Session = Depends(get_current_session)): ...

@router.get("/me/profile")                  # account scope
async def profile(user: User = Depends(get_current_user)): ...
```

Testing in Swagger: the **Authorize** button holds one token at a time, so you have to swap
between the user token and the session token. Register → authorize with the user token →
`POST /auth/session` → re-authorize with the session token. With the session token active,
`POST /auth/session` must return **401** — that response is the privilege boundary working.

Design notes and the remaining trade-offs (blocking DB calls in async handlers, the denylist
read per request, `purge_expired_tokens` having no scheduler) are in the module docstrings of
`app/api/v1/auth.py` and `app/utils/auth.py`.

## Run the Streamlit UI

In a second terminal (`app.main:app` must be running):

```bash
export API_BASE_URL=http://localhost:8000
uv run streamlit run app/ui/main.py --server.port 8501
```

`API_BASE_URL` is the API origin only — the client appends `/api/v1` itself.

Sign in or create an account on first load; every endpoint behind the UI requires a bearer
token, so there is no anonymous mode. Once in, the sidebar lists your conversations straight
from Postgres (`GET /auth/sessions`) and opening one loads its history from the LangGraph
checkpointer (`GET /chatbot/messages`), so a conversation started on another machine — or
before a restart — is still there. Rename, clear and delete act on the open conversation.

Chat is one turn per request against `POST /chatbot/chat`. Plan builds, changes, reviews and
reverts all answer through the same endpoint, including the confirm gate: when the agent asks
whether to apply a change, replying `yes` resumes the interrupted run.

Tokens live in Streamlit's per-session state and nowhere else — not in the URL, not on disk —
so a full browser reload signs you out. Nothing is lost: the conversations are in the
database and reappear on the next sign-in.

## Run in Docker

```bash
docker build -t pt-ai-core .
docker run -p 8000:8000 \
  -e POSTGRES_HOST=host.docker.internal -e POSTGRES_PORT=5433 \
  -e OPENAI_API_KEY=... -e JWT_SECRET_KEY=... \
  pt-ai-core
```

Runs as a non-root user and is healthchecked on `/health`.

## Configuration

All settings come from environment variables (see `.env.example` for the full list).

`app/` loads exactly one env file, picked by first match: `.env.<APP_ENV>.local` →
`.env.<APP_ENV>` → `.env.local` → `.env`. Docker Compose separately reads only `.env` for
`${VAR}` interpolation inside `docker-compose.yml` — it cannot read `.env.development`,
which is why both files exist.

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | — | **Required.** Under 32 characters and the app refuses to start. `openssl rand -hex 32`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access tokens are short-lived because revoking them costs a denylist read. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lifetime of the rotating refresh credential. |
| `AUTH_DATABASE_URL` | — | Overrides the `POSTGRES_*` parts for the auth tables. Set to `sqlite:///./auth_dev.db` to run without a database container. |
| `ALLOWED_ORIGINS` | `*` | Must be set to explicit origins — the app refuses to start on a wildcard while credentials are allowed. |
| `LOG_LEVEL` | `INFO` | Applied at API startup. |
| `LOG_FORMAT` | `json` | `json` for machine-parseable production logs, `text` for readable local output. |

## Project layout

```text
app/
├── main.py         # ASGI entrypoint (app.main:app) — what the Dockerfile runs
├── api/v1/         # routers; auth.py holds the two auth dependencies
├── core/
│   ├── configs/    # pydantic-settings; resolves the env file from the project root
│   ├── logging.py  # structlog + per-request context binding
│   ├── limiter.py  # slowapi
│   └── middleware.py
├── models/         # SQLModel tables: user, session, refresh_token, revoked_token
├── schemas/        # pydantic request/response models
├── services/       # DatabaseService — all persistence for the auth layer
├── utils/          # token creation/verification, input sanitization
└── ui/             # Streamlit client — HTTP-only, talks to /api/v1 and nothing else
alembic/            # migrations for the app/ schema only
```

Layer rule: `api → services → models`. `utils/` and `core/` are leaves that everything may
import and that import nothing from the layers above them. `ui/` sits outside that rule
entirely: it is a client of the HTTP surface, so it may import `app.utils` for shared
validation constants but never a service, a model or the graph.

