# Known Issues

Open defects found during the architecture cleanup (branch `chore/architecture-cleanup`,
2026-07-30) that were **not fixed**, because fixing them would have changed application
logic or fallen outside the agreed scope.

Each entry records what is wrong, how to reproduce it, and what a fix would involve.
Kept at the repo root deliberately: `docs/` is gitignored (`.gitignore:20`), so anything
filed there is not version-controlled.

Status legend: **OPEN** · **MITIGATED** (symptom handled, cause remains) · **FIXED**

---

## ISSUE-1 — LLM-invented `category` filter silently empties knowledge-base retrieval

**Severity: High · Status: FIXED (2026-07-30) · Production-affecting**

> **Resolution.** `RetrievalService.search` now retries once with only the inferred
> `category` dropped when a filtered search returns zero candidates. Caller-supplied
> `goal`/`equipment` filters stay enforced, so the retry can only recover results a
> hallucinated category excluded — it cannot widen a search that already found something,
> and a genuinely irrelevant query still returns nothing. The relaxation is logged at INFO
> so the rate of hallucinated categories stays observable.
>
> Locked in by three tests in `tests/test_retrieval_service.py`, which use a fake
> repository reproducing Postgres' hard-filter semantics — no live LLM or database needed.
> Verified the main one fails when the fix is reverted.
>
> Options 1 and 2 below were **not** taken: both change behaviour for searches that
> currently succeed, whereas the retry only affects the zero-result path where the current
> behaviour is already "return nothing". They remain the better long-term fix if
> hallucinated categories turn out to be common — the new log line will show that.
>
> Original diagnosis follows.

`LlmQueryRewriter` asks the LLM to infer metadata filters, and returns a
`MetadataFilters.category` value it invented. That value is then applied as a **hard SQL
constraint** (`guideline_repository.py:48-49`, `d.category = %(category)s`). When the
LLM's guess does not exactly match a document's `category` column, the document is
excluded — so retrieval returns **nothing at all** rather than degrading to an unfiltered
search.

This is the cause of the one persistently failing test,
`tests/test_fitness_mcp_server.py::test_search_guidelines_returns_seeded_document`.
The test seeds a document with `category="general"`; the rewriter infers
`category="progressive_overload"` for the query `"progressive overload training volume"`,
and the seeded document is filtered out.

**Reproduction** (requires Postgres and a real `OPENAI_API_KEY`):

```
seed one document, query "progressive overload training volume"

  repo.search (vector only, no pipeline)          -> 1 hit
  pipeline, fitness_kb_query_rewrite_enabled=False -> 1 hit
  pipeline, fitness_kb_query_rewrite_enabled=True  -> 0 hits   <-- default

same doc, same query, only the document's category changed:
  category="general"              -> 0 hits
  category="progressive_overload" -> 1 hit
```

Not a threshold problem: it returns 0 hits even with `min_similarity=0.0`.

**Why it matters.** `fitness_kb_query_rewrite_enabled` defaults to `True`, so this is the
production path. Any query whose inferred category does not match the corpus taxonomy
returns zero guidelines, and the caller cannot distinguish "no relevant guidelines" from
"filter excluded everything". `search_guidelines` then reports
`sufficient_coverage=False`, pushing research to external sources instead of the curated
knowledge base — a silent quality regression, not a visible error.

**Possible fixes** (each changes behaviour, hence deferred):
1. Treat LLM-inferred filters as *soft* signals — use them for ranking, not exclusion.
2. Constrain the LLM to the categories actually present in the corpus, and drop any value
   outside that set.
3. Retry without metadata filters when a filtered search returns zero rows.

Option 3 is the smallest change and preserves current behaviour whenever results exist.

---

## ISSUE-2 — `get_settings()` cache is polluted by orchestrator background threads

**Severity: Medium · Status: MITIGATED (three call sites), cause OPEN**

`get_settings()` is `@lru_cache`d process-wide. `RunOrchestrator` spawns four kinds of
background thread (`graph/service.py:538,684,816,885`) and calls `get_settings()` at five
sites. Those threads outlive the test that started them — visible as `PoolClosed` warnings
arriving after teardown.

When a leaked thread calls `get_settings()` *after* `conftest.py`'s monkeypatched
environment has been restored, it repopulates the cache from the real `.env` — including
live `LANGFUSE_*` keys. Any later test reading `get_settings()` then observes production
configuration.

This made three assertions in `tests/test_e2e_happy_path.py` fail roughly **1 run in 4**.
Those three now build `Settings` directly instead of reading the global cache, which is
deterministic regardless of what a leaked thread does. Measured after the change: 0
failures in 10 consecutive runs (was ~1 in 4).

**The leak itself is unfixed.** Any future test that reads `get_settings()` for a value the
local `.env` overrides is exposed to the same race. A real fix would join orchestrator
threads at teardown, or give the orchestrator an explicit injected `Settings`.

This is the concrete instance of S6/S7 in
`docs/reports/architecture_restructure_review_2026-07-30.md`.

---

## ISSUE-3 — Rare unattributed flake in Postgres + background-thread tests

**Severity: Low · Status: OPEN**

Roughly 3 times in ~30 full local runs, one of these failed and then passed on re-run:

- `tests/test_e2e_happy_path.py::test_e2e_happy_path_persists_final_artifact`
- `tests/test_graph_service.py::test_start_resume_run_rejects_a_second_concurrent_resume_via_the_database_claim`

Both pass in isolation (3/3) and in 5 consecutive full runs afterwards. Both involve real
Postgres plus background threads, so ISSUE-2's thread leak is the likely neighbourhood.

**Honest caveat:** this was *not* observed in a 5-run sample of the pre-cleanup baseline
(commit `7938167`). That sample is too small to establish whether the flake pre-existed or
was introduced. Needs a longer run (30+) on both revisions to attribute.

---

## ISSUE-4 — A test makes live, billable API calls on every local run

**Severity: Medium · Status: MITIGATED**

`tests/test_ragas_benchmark.py::test_ragas_benchmark_script_runs` spawns
`scripts/ragas_benchmark.py` as a **subprocess**. The subprocess does not inherit
`conftest.py`'s mock wiring, so it runs the real Research → Fitness → Verification
pipeline against live models whenever `OPENAI_API_KEY` is set. That also made it fail
intermittently on network/API variance.

A `skipif(not get_settings().openai_api_key)` guard now matches the convention already used
in `tests/test_fitness_mcp_server.py`, so CI without secrets is unaffected. **It still
spends real tokens on any local run with keys present.**

A proper fix would give the subprocess a mocked configuration via environment variables
rather than relying on the caller's `.env`.

---

## ISSUE-5 — The test suite hangs, rather than fails, when Postgres is unavailable

**Severity: Medium · Status: MITIGATED in CI, OPEN locally**

With no Postgres on the configured port, tests block on `psycopg` pool timeouts; a full run
exceeded **10 minutes** instead of the usual ~25 s. There is no fail-fast check.

`.gitlab-ci.yml`'s `test` job now probes the connection before invoking pytest and errors in
under a second. Locally there is still nothing to tell you the container is down — the
suite just appears to hang. A session-scoped fixture asserting connectivity would fix it
for both.

---

## ISSUE-6 — `DATABASE_URL` silently shadows every `POSTGRES_*` setting

**Severity: Low (config foot-gun) · Status: OPEN**

`Settings.checkpointer_dsn` (`config/settings.py:255-261`) returns `database_url` verbatim
when it is set, ignoring `postgres_host`, `postgres_port`, `postgres_user`,
`postgres_password` and `postgres_db` entirely. Because this repo's `.env` sets
`DATABASE_URL`, overriding `POSTGRES_HOST`/`POSTGRES_PORT` appears to do nothing, with no
warning.

This cost real debugging time while writing CI. A fix would either log when both are
present, or drop the composite fields in favour of a single DSN.

---

## ISSUE-7 — Uvicorn's own logs bypass the structured logging configuration

**Severity: Low · Status: OPEN**

`core/observability/logging.py` configures the root logger, so application records are
emitted as JSON with `run_id`/`thread_id`. Uvicorn installs its own handlers on the
`uvicorn`, `uvicorn.error` and `uvicorn.access` loggers with `propagate=False`, so its
startup and access lines remain plain text:

```
INFO:     Started server process [69716]
{"timestamp": "...", "level": "ERROR", "logger": "api.deps", "message": "...", "run_id": null}
INFO:     127.0.0.1:56291 - "GET /health HTTP/1.1" 200 OK
```

A log aggregator will therefore see two formats on stdout. The fix is to pass a matching
`log_config` at the uvicorn entrypoint.

---

## ISSUE-8 — Benchmark-only evaluation modules still ship in the production wheel

**Severity: Low · Status: OPEN (deliberately deferred)**

`ragas` is no longer a runtime dependency (it is now the `eval` extra), which removes
~180 MB of `ragas`/`datasets`/`pandas`/`pyarrow` from production images. But three modules
that only scripts and tests use still ship inside `core`:

- `core/evaluation/owasp_prompt_benchmark.py`
- `core/evaluation/owasp_prompt_robustness.py` (858 lines)
- `core/evaluation/ragas_benchmark.py`

They cannot simply move: `core/evaluation/shadow_eval.py` is imported **eagerly** by
`api/deps.py:8` and `api/main.py:12`, and `core/evaluation/ragas.py` is reached lazily from
the production faithfulness path, so `core/evaluation/` cannot leave the package wholesale.
Relocating only the three benchmark modules touches ~6 test files and both benchmark
scripts.

---

## Note on `docs/`

`.gitignore:20` ignores the entire `docs/` tree, including `docs/reports/` and
`src/docs/`. Every architecture review and workflow document in this repository is
therefore untracked. If that is unintentional, the reports are one `git add -f` away from
being version-controlled — and this file should move under `docs/` once it is.
