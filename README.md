# PT AI Core Deep Researcher

Supervisor-orchestrated LangGraph system for **training plans** and **macro coaching**. Phase 1 includes planning, Tavily MCP research, fitness synthesis, verification, HITL approval, persistence, LangFuse tracing, and a faithfulness benchmark.

---

## Migration in progress: `src/` → `app/`

> ⚠️ **`src/` is being retired.** A new structure is being built in `app/`, and the two
> trees currently coexist. Read this before touching either.

| | `src/` (legacy) | `app/` (new) |
|---|---|---|
| Status | **deprecated — will be deleted** | active development |
| ASGI entrypoint | `api.main:create_app` | `app.main:app` ← what the Dockerfile runs |
| Persistence | psycopg3 + `CREATE TABLE IF NOT EXISTS` DDL in each store | SQLModel + Alembic migrations |
| Settings | `src/core/config/settings.py` | `app/core/configs/config.py` |
| Rate limiting | `AIRateLimiter` (token/cost, Postgres-backed) | slowapi (per-IP, on auth endpoints) |
| Auth | **none** | JWT dual-token — see [Authentication](#authentication-app-flow) |

Rules while both exist:

- **Write new code in `app/`.** Do not add to `src/`.
- **Do not import across the boundary.** `app/` must not import from `src/`, and vice versa.
  Nothing does today; keeping it that way is what makes the deletion a delete rather than a
  refactor.
- **Port, do not copy.** `src/` carries known defects (see the TODO below). Copying a route
  across carries them with it.

### TODO — retiring `src/`

- [ ] Port the run/HITL endpoints (`/runs`, `/runs/{id}/resume`, `/runs/{id}/events`) into
      `app/api/v1/`, guarded by `get_current_session`
- [ ] Port `RunOrchestrator` and the LangGraph wiring under `app/services/`
- [ ] Move the `adapters/` stores (`run_history_store`, `run_tracker`, `idempotency_store`,
      `guideline_repository`, `template_repository`) onto SQLModel + Alembic, or document
      why a given store stays on raw psycopg
- [ ] Decide the fate of `AIRateLimiter` — the token/cost limiter has no equivalent in
      `app/`, and slowapi does not replace it
- [x] Port the Streamlit UI's API client to the `app/` endpoints and the bearer-token flow —
      moved to `app/ui/`, `src/ui/` deleted
- [ ] Move `tests/` fixtures and the OWASP/Ragas benchmark harnesses over
- [ ] Delete `src/`, drop it from `[tool.hatch.build.targets.wheel]` and
      `[tool.pytest.ini_options].pythonpath`, update `.gitlab-ci.yml`

**Fix during the port, not after — these are live defects in `src/`:**

- [ ] `GET /users/{user_id}/runs` takes `user_id` straight from the URL with **no
      authentication**. Anyone who knows a user id can read that user's run history. The
      replacement must derive the id from the token, never from the path.
- [ ] Audit every other `src/` route for the same pattern before porting it.

---

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
uv run python scripts/ingest_knowledge.py   # embeds the guideline corpus — see below
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
uv run ruff check app src tests scripts
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

## Run the API (`app/` flow)

This is the entrypoint the Dockerfile uses.

```bash
docker compose up -d db          # Postgres on host port 5433
uv sync --extra dev
uv run alembic upgrade head      # creates user / session / refresh_token / revoked_token
uv run python scripts/seed_catalog.py     # exercise catalog
uv run python scripts/seed_knowledge.py   # knowledge base (needs OPENAI_API_KEY)
uv run uvicorn app.main:app --reload
```

Swagger UI: **http://localhost:8000/docs**

### Seeding the knowledge base (`app/` flow)

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

### Authentication (`app/` flow)

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
the path or body — that is exactly the defect `src/` has:

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

## Run the legacy API (`src/` flow)

> Deprecated. See [Migration in progress](#migration-in-progress-src--app).

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints (**none of these are authenticated**):

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

## Embedding data for RAG

The Fitness Knowledge Store is the curated corpus the agent prefers over live web
research. Getting data into it is one command, but what that command does is worth
knowing before you add your own documents.

### The pipeline

```text
corpus.jsonl → JSONLLoader → Validator → SimpleChunker → OpenAI embeddings → Postgres (pgvector)
```

```bash
uv run python scripts/bootstrap_fitness_db.py   # creates tables + the vector/FTS indexes
uv run python scripts/ingest_knowledge.py       # embeds and upserts every record
# -> Ingested 9 sources, 9 documents, 9 chunks.
```

Both are **idempotent** (`ON CONFLICT DO UPDATE` throughout) — re-run them after editing the
corpus and existing rows are replaced, not duplicated. Ingestion writes straight to Postgres,
bypassing MCP: it is an admin/seeding operation, not something an agent does at runtime.

Requires `OPENAI_API_KEY` — every chunk is embedded for real.

### The corpus

`src/core/shared/knowledge/data/corpus.jsonl` — one JSON object per line:

```json
{
  "id": "hypertrophy-volume-guideline",
  "title": "Hypertrophy Weekly Set Volume",
  "content": "Most muscle groups respond well to roughly 10-20 hard sets per week ...",
  "category": "hypertrophy",
  "tags": ["volume", "sets", "hypertrophy"],
  "goal_applicability": ["muscle_gain", "recomposition", "general_fitness"],
  "equipment_applicability": ["gym", "home", "bodyweight"],
  "source_type": "guideline",
  "source_url": "local-kb://hypertrophy-volume-guideline",
  "published_year": null,
  "reviewed_at": null,
  "trust_score": 0.95
}
```

To add your own data, append records and re-run `ingest_knowledge.py`. Three fields do more
work than they look like they do:

- **`category`** is a retrieval **filter**, not a label. The query rewriter infers a category
  from the user's question and it is applied as a hard SQL constraint, so a document whose
  category does not match is excluded outright. Keep the vocabulary small and consistent.
  (If a filtered search returns nothing, retrieval now retries once without the inferred
  category — otherwise a mismatch would silently return zero results.)
- **`goal_applicability` / `equipment_applicability`** are filtered against the caller's
  profile. Leave them broad unless a document genuinely only applies to one setup.
- **`trust_score`** feeds `has_sufficient_coverage`, which decides whether the agent can skip
  external web research. Documents below the caller's `min_trust_score` (default `0.85`)
  will not satisfy coverage on their own.

### Tuning

| Setting | Default | Notes |
|---|---|---|
| `FITNESS_KB_EMBEDDING_MODEL` | `text-embedding-3-small` | **Coupled to the schema** — see below |
| `FITNESS_KB_CHUNK_MAX_CHARS` | `2000` | Chunk size |
| `FITNESS_KB_CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `FITNESS_KB_MIN_SIMILARITY` | `0.4` | Cosine floor for dense retrieval |
| `FITNESS_KB_QUERY_REWRITE_ENABLED` | `true` | LLM query understanding before retrieval |
| `FITNESS_KB_RERANK_ENABLED` | `true` | LLM relevance rerank after fusion |

> **Changing the embedding model is not a config-only change.** The chunks table declares
> `embedding vector(1536)`, matching `text-embedding-3-small`. A model with different
> dimensions requires editing that DDL in `core/adapters/db/bootstrap.py`, dropping the
> table, and re-ingesting — the mismatch will otherwise fail at insert time.

### Verifying it worked

```bash
uv run python -c "
from core.config.settings import get_settings
from core.shared.knowledge.embeddings import get_embedding_provider
from core.adapters.db.guideline_repository import GuidelineRepository
from core.shared.knowledge.retrieval_service import build_retrieval_service
s = get_settings(); repo = GuidelineRepository(s.checkpointer_dsn)
svc = build_retrieval_service(repo, get_embedding_provider(s), s)
for h in svc.search(kind='guideline', query='how many sets per week for hypertrophy',
                    goal='muscle_gain', equipment='gym', limit=3,
                    min_similarity=s.fitness_kb_min_similarity):
    print(f'{h.document_id:38} sim={h.similarity:.3f} trust={h.trust_score}')
repo.close()"
```

Retrieval is hybrid: pgvector cosine **and** Postgres full-text search, fused with reciprocal
rank fusion, then reranked. So a document can surface on keyword match even when its
embedding similarity is mediocre.

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

Note that the two flows read **different** files. `app/` loads exactly one env file, picked
by first match: `.env.<APP_ENV>.local` → `.env.<APP_ENV>` → `.env.local` → `.env`. Docker
Compose separately reads only `.env` for `${VAR}` interpolation inside `docker-compose.yml`
— it cannot read `.env.development`, which is why both files exist.

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | — | **Required by `app/`.** Under 32 characters and the app refuses to start. `openssl rand -hex 32`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access tokens are short-lived because revoking them costs a denylist read. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lifetime of the rotating refresh credential. |
| `AUTH_DATABASE_URL` | — | `app/` only. Overrides the `POSTGRES_*` parts for the auth tables. Set to `sqlite:///./auth_dev.db` to run without a database container. Deliberately not named `DATABASE_URL`, which the legacy flow already uses with a psycopg2-style prefix. |
| `ALLOWED_ORIGINS` | `*` | Must be set to explicit origins — `app/` refuses to start on a wildcard while credentials are allowed. |
| `DATABASE_URL` | — | Legacy `src/` flow. **Takes precedence over every `POSTGRES_*` variable.** Setting `POSTGRES_HOST`/`POSTGRES_PORT` has no effect while this is set. |
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

Two trees, one of them on its way out — see
[Migration in progress](#migration-in-progress-src--app).

### `app/` — the new structure

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

### `src/` — legacy, scheduled for deletion

```text
src/
├── api/            # FastAPI app — routes, DI wiring, schemas
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

CI still describes the `src/` layout. Part of retiring `src/` is updating `lint` to cover
`app`, `build` to assert the wheel ships `app`, and `runtime-deps` to import `app.main`
rather than `api.main`.
