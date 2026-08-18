# PT AI Core Deep Researcher

LangGraph system for **training plans** and **macro coaching**: a supervisor agent that
plans, changes, reviews and answers, with knowledge-base retrieval, rubric verification, a
human confirm gate, persistence, JWT auth and LangFuse tracing, behind a FastAPI service
with a Streamlit front end.

The order of steps is a decision the supervisor re-makes after every tool result, not a
property of a graph — so the guarantees that matter live where a model cannot skip them:
in middleware, in tool bodies, and in a draft store that hands out handles instead of plan
JSON.

| Document | What it covers |
|---|---|
| [docs/supervisor-architecture.md](docs/supervisor-architecture.md) | What runs, why it is a supervisor rather than a router, and what that costs |
| [docs/workflow.md](docs/workflow.md) | The domain rules: plan shapes, the profile gate, the three rubric checks, confirm and revert |
| [docs/memory.md](docs/memory.md) | The four memory layers, who writes each, and where they must not mix |
| [docs/authentication.md](docs/authentication.md) | Token scopes, the privilege boundary, and the auth checklist |
| [docs/diagrams/](docs/diagrams/) | Generated Mermaid topologies, one per compiled graph |

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
| `dev` | `uv sync --extra dev` | pytest, pytest-asyncio, ruff, pre-commit |
| `evals` | `uv sync --extra evals` | ragas, for the retrieval metrics in `evals/` |

## Run tests

```bash
uv run pytest
uv run ruff check app tests scripts evals
```

The suite needs no secrets and makes no network calls: every agent holds a chat model
directly — `create_agent` needs one — so `tests/conftest.py` patches `LLMRegistry.get_llm`
with a scripted `FakeChatModel`. All four agents resolve their model through
`app.core.langgraph.runtime.models`, which is why that is one patch rather than one per package;
an agent added later is stubbed by the same call instead of reaching the network until
someone notices.

The auth suite runs against a throwaway SQLite file and **must run in its own process**:

```bash
uv run pytest tests/test_auth_flow.py -v
```

In a whole-suite run it errors out on purpose. Another module has already imported `app.*`
by then, so `AUTH_DATABASE_URL` arrives too late and `engine` is still bound to the real
Postgres — carrying on would drop that database's tables. The refusal names the fix.

Two of those tests are the privilege boundary between the token scopes —
`test_session_token_cannot_create_session` and
`test_user_token_cannot_reach_session_endpoint`. A failure there is a security regression,
not a flaky test.

### What the suite guards in the graph

The old root graph proved three properties by reading edges. There are no edges left to
read, so those proofs were replaced by two kinds of test, and the first is worth more than
the second:

- **Static** (`tests/test_app_supervisor.py`): no subagent's tool set contains a write
  tool, `save_plan` has no `plan` parameter, no plan-producing tool accepts a `profile`,
  only `commit_draft` and `restore_version` can mint a draft handle, every minted draft
  carries macros, and no function in the scoring path has a parameter a transcript could
  arrive in. All six run without a model.
- **Behavioural** (`tests/test_app_turn.py`): the confirm gate end to end — a plan is shown
  and not saved, "yes" saves the plan that was shown, anything else leaves it alone.
  Slower and weaker than an edge, and the honest price of the architecture
  ([§11.2](docs/supervisor-architecture.md)).

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
uv run alembic upgrade head      # every app/ table
uv run python scripts/seed_catalog.py     # exercise catalog (~100 rows)
uv run python scripts/seed_config.py      # template library + rubrics
uv run python scripts/seed_knowledge.py   # knowledge base (needs OPENAI_API_KEY)
uv run uvicorn app.main:app --reload
```

The seed files are validated separately from being loaded, and the validators run
**before** the seeder — the faults they catch are the silent kind (two templates sharing a
`slot_id`, rubrics disagreeing on `rubric_version`, a slot naming a movement pattern the
taxonomy does not define):

```bash
uv run python scripts/check_config_seed.py
uv run python scripts/check_exercise_seed.py
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

The knowledge base is one of four things this application calls memory. What each layer
holds, who writes it, and where they must not be mixed is in
[docs/memory.md](docs/memory.md).

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

The conversation surface is four routes, all session-scoped:

| Method | Path | Guard |
|--------|------|-------|
| `POST` | `/api/v1/chatbot/chat` | session token, 30/min |
| `POST` | `/api/v1/chatbot/chat/stream` | session token, 20/min |
| `GET` | `/api/v1/chatbot/messages` | session token, 50/min |
| `DELETE` | `/api/v1/chatbot/messages` | session token, 50/min |

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

Chat is one turn per request against `POST /chatbot/chat/stream`. Tokens appear in the
chat window as the supervisor writes them. Plan builds, changes, reviews and reverts all
answer through the same endpoint, including the confirm gate: when the agent shows a plan
and asks whether to keep it, the question is the last chunk of that stream (the interrupt
fires after the model tokens, if any, have ended). Replying `yes` resumes the interrupted
run and saves the plan you were shown — not one rebuilt from the transcript. Anything that
is not a recognised yes is treated as no, and leaves the stored plan exactly as it was.

`POST /chatbot/chat` is the non-streaming counterpart of the same turn: it waits for the
graph to finish and returns the completed messages in one body.

Tokens live in Streamlit's per-session state and nowhere else — not in the URL, not on disk —
so a full browser reload signs you out. Nothing is lost: the conversations are in the
database and reappear on the next sign-in.

## Export graph diagrams

Regenerate Mermaid diagrams for the supervisor and every agent into `docs/diagrams/`.
Compiles without a checkpointer, so Postgres is not required.

```bash
uv run python scripts/export_graph_diagrams.py                     # every graph
uv run python scripts/export_graph_diagrams.py --graph supervisor  # just one
uv run python scripts/export_graph_diagrams.py --format png        # also render PNG
```

These pictures now show less than they used to, and that is the architecture rather than a
regression. An agent's internal graph is fixed — a `model` node, a `tools` node, and one
node per middleware hook — so the diagram tells you which hooks are wired and nothing about
what the model will choose to call. No graph left in the registry has arbitrary nodes and
edges: `verification` did, and it is now plain functions called from tool bodies.

Only `.mmd` is written by default, and only it is committed. PNG is opt-in because
rendering posts the markup to the public mermaid.ink service, which rejects the identifiers
`create_agent` generates for a middleware named `ToolCallLimitMiddleware[commit_draft]` —
and half a set of PNGs is worse than none. Pass `--draw-method pyppeteer` to render locally
when a picture is actually wanted.

## Offline evaluation

`evals/` scores turns that **already happened**. It reads finished traces from Langfuse,
judges them, and writes the scores back. Nothing here gates a request: `evals` imports
from `app`, and `app` never imports from `evals`, so an eval cannot change a turn's
outcome even by accident.

```bash
uv sync --extra evals
uv run python -m evals.run --scope traces --max-items 50        # domain judges
uv run python -m evals.run --scope observations --max-items 25  # ragas over search_knowledge
```

Two scopes because they see different data. `traces` runs the domain judges over a whole
turn — helpfulness, relevancy, conciseness, hallucination, toxicity, plus four this
application's own rules imply: `plan_safety`, `macro_consistency`, `confirm_discipline`
and `verdict_grounding`. `observations` runs Ragas faithfulness and context precision over
a single `search_knowledge` retrieval and the passages it returned; it is capped lower
because those metrics are multi-call by construction.

Needs `LANGFUSE_*` keys and `EVALUATION_API_KEY` (falls back to `OPENAI_API_KEY`). There
is no report file — `BatchEvaluationResult` carries the per-evaluator stats, and Langfuse
itself is the dashboard.

A regression an eval catches is a **quality** regression. Anything that must fail hard
belongs in the rubric checks or in `tests/`.

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
| `APP_ENV` | `development` | Picks the env file, and tags every Langfuse trace with the environment. |
| `JWT_SECRET_KEY` | — | **Required.** Under 32 characters and the app refuses to start. `openssl rand -hex 32`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access tokens are short-lived because revoking them costs a denylist read. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lifetime of the rotating refresh credential. |
| `AUTH_DATABASE_URL` | — | Overrides the `POSTGRES_*` parts for the auth tables. Set to `sqlite:///./auth_dev.db` to run without a database container. |
| `ALLOWED_ORIGINS` | `*` | Must be set to explicit origins — the app refuses to start on a wildcard while credentials are allowed. |
| `KNOWLEDGE_MIN_SCORE` | `0.3` | Floor for `search_knowledge`. Vector search always returns a full `top_k`, so without a threshold an out-of-scope question gets the least-related passages — and the model cites them. Returning `[]` is the correct answer. |
| `SESSION_NAMING_ENABLED` | `true` | Names a conversation from its first message, in the background. |
| `LOG_LEVEL` | `INFO` | Applied at API startup. |
| `LOG_FORMAT` | `json` | `json` for machine-parseable production logs, `text` for readable local output. |

## Project layout

```text
app/
├── main.py            # ASGI entrypoint (app.main:app) — what the Dockerfile runs
├── api/v1/            # routers: auth.py (+ the two auth dependencies), chatbot.py
├── core/
│   ├── configs/       # pydantic-settings; resolves the env file from the project root
│   ├── langgraph/     # the agent system — see below
│   ├── observability/ # Langfuse handler package, attached at the root config
│   ├── logging.py     # structlog + per-request context binding
│   ├── limiter.py     # slowapi; Valkey-backed when VALKEY_HOST is set
│   └── middleware.py
├── models/            # SQLModel tables: user, session, tokens, exercises, templates,
│                      #   rubrics, user_profile, plan_versions, knowledge_chunks
├── schemas/           # pydantic request/response models + the types agents exchange
├── services/          # persistence and pure domain logic: catalog, templates, rubrics,
│                      #   nutrition, profile, versions, knowledge, episodes, llm/
├── utils/             # token creation/verification, input sanitization
└── ui/                # Streamlit client — HTTP-only, talks to /api/v1 and nothing else
alembic/               # migrations for the app/ schema only
data/                  # seed files: exercises, templates, rubrics, knowledge/*.docx
scripts/               # seeding, seed validation, diagram export
evals/                 # offline scoring of finished Langfuse traces — imports app/,
                       #   and app/ never imports it
tests/                 # pytest; test_auth_flow.py runs in its own process
```

Layer rule: `api → services → models`. `utils/` and `core/` are leaves that everything may
import and that import nothing from the layers above them. `ui/` sits outside that rule
entirely: it is a client of the HTTP surface, so it may import `app.utils` for shared
validation constants but never a service, a model or the graph.

### Inside `core/langgraph/`

```text
core/langgraph/
├── graph.py          # the facade the API calls — four methods, and the only thing that
│                     #   knows about the checkpointer pool or a chat turn
├── prompts/          # shared .md prompts: classify, extract_profile, session title/summary
├── supervisor/
│   ├── agent.py      # build_supervisor_with() — create_agent + middleware + the confirm gate
│   ├── middleware.py # topic_gate · load_context · extract_profile · dynamic_prompt
│   ├── tools.py      # planning_agent · review_agent · qa_agent · list/restore · save_plan
│   ├── state.py      # SupervisorState — eight fields, all of which outlive the turn
│   └── prompts/      # supervisor.md — system prompt owned by the supervisor
├── agents/
│   ├── __init__.py   # the registry: one line per agent, built once and cached
│   ├── planning/     # build and change, as one agent with mode="build"|"change"
│   ├── review/       # assessing a plan the user pasted in; mints no handle, so saves none
│   └── qa/           # knowledge questions; read-only, and the only holder of estimate_macros
├── routing/          # the classifier the topic gate calls; its intent is advisory
├── profile/          # extraction cleanup and goal-conflict detection
├── checks/           # macro · volume · injury — one pure function per rubric, no graph
├── drafts/store.py   # verified plans held by handle between producing and saving
├── scoring.py        # macros and the three checks, in one call — score()
├── rendering.py      # every string a model is allowed to see about a plan
├── diff.py           # what a save is about to change, for the confirm question
├── versioning.py     # rendering the version index; what a restore re-checked
└── models.py         # which model an agent runs on, and its retry/fallback middleware
```

Three rules the layout enforces, each of which replaced a graph edge:

1. **Only `commit_draft` and `restore_version` mint a handle**, and `save_plan` accepts
   nothing but one. Plan JSON never passes through the supervisor's context, so no model
   can retype a set count on its way to being stored.
2. **The profile gate is a precondition inside every plan-producing tool**, never a tool of
   its own. Given `check_profile()` as an option, a model eventually decides the profile
   looks complete and proceeds with a missing activity level.
3. **The verifier has nowhere to put a transcript.** `score(plan, profile, scope)` is a
   plain function with no argument a message list could arrive in, so the verifier cannot
   see how the plan was built even by accident.

Adding an agent is a new package plus one line in `agents/__init__.py`. If it also requires
editing the supervisor, a schema and a route, the seam is in the wrong place.

