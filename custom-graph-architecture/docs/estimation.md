# Estimation & progress

Task breakdown from the implementation-detail spec (PDF pp. 27–30). Total estimate **56h / 7 days**.
Update `Actual` and `Status` as each task lands.

Status values: `Todo` · `In progress` · `Done`

## Milestone 1 — Project initialization & setup (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 21/08 | Init LangGraph project structure (repo layout, package/dependency setup) | 1 | 1 | Done |
| 21/08 | Setup PostgreSQL instance + `AsyncPostgresSaver` checkpointer config | 1 | 1 | Done |
| 21/08 | Enable pgvector extension & base `PostgresStore` setup | 0.5 | 0.5 | Done |
| 21/08 | Define `GraphState` schema (input, guard, context, coaching, HITL, QA, output) | 0.5 | 0.5 | Done |
| 21/08 | Setup Docker + Docker Compose (app, Postgres, pgvector) | 0.5 | 1 | Done |
| 21/08 | Base Langfuse project/tracing wiring | 0.5 | 1 | Done |

## Milestone 2 — Guard & intent classification (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 21/08 | Implement `llm_guard` node (integrate llm-guard input scanning) | 1 | 1.5 | Done |
| 21/08 | Implement `blocked` node (return block message, stop immediately) | 0.5 | 0.5 | Done |
| 21/08 | Implement `classify_intent` node (coaching / qa / off_topic) | 0.5 | 0.5 | Done |
| 21/08 | Implement `off_topic` node | 0.5 | 0.5 | Done |
| 21/08 | Wire routing edges: `llm_guard` → `classify_intent` → 3 branches | 0.5 | 0.75 | Done |
| 21/08 | Unit tests: guard scanning + intent classification accuracy | 1 | 1.5 | Done |

Guard and intent routing are now wired (`llm_guard` → `blocked` / `classify_intent` →
`coaching` / `qa` / `off_topic`). Guard scanning tests, intent routing tests and live
classifier accuracy checks are all passing.

## Milestone 3 — Context loading branch (5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 22/08 | Implement `load_context` node (load profile & plan) | 1 | 1 | Done |
| 22/08 | Implement `determine_context` node (identify missing fields) | 1 | 0.5 | Done |
| 22/08 | Implement `request_missing_info` node | 0.5 | 0.5 | Done |
| 22/08 | Implement `wait_for_user` node (`interrupt()` pause/resume) | 1 | 1 | Done |
| 22/08 | Implement `save_user_data` node (persist reply to DB before reload) | 1 | 1 | Done |
| 22/08 | Wire routing edges for context-complete / missing-fields branch | 0.5 | 0.5 | Done |

## Milestone 4 — Coach agent & tools (5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 22/08 | Implement `write_todo` node | 1 | 1 | Done |
| 22/08 | Implement `coach_agent` core (LangGraph agent + tool binding) | 1 | 1 | Done |
| 22/08 | Implement `load_template` tool | 0.5 | 0.5 | Done |
| 22/08 | Implement `load_exercise` tool | 0.5 | 1 | Done |
| 24/08 | Implement `calc_macro` tool (shared calorie/macro calculation) | 0.5 | 0.5 | Done |
| 22/08 | Implement Pydantic schemas (`UserProfile`, `Injury`, `Exercise`, `WorkoutTemplate`, …) | 0.5 | 1 | Done |
| 22/08 | Implement enums (`Sex`, `ActivityLevel`, `FitnessGoal`, `MovementPattern`, `EquipmentType`, …) | 0.5 | 0.5 | Done |
| 24/08 | Unit tests for coach agent + tools | 0.5 | 0.5 | Done |

## Milestone 5 — Deterministic verification gate (7h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 24/08 | Implement schema completeness check | 1 | 1 | Done |
| 24/08 | Implement macro consistency check | 1 | 1 | Done |
| 24/08 | Implement training volume & schedule check | 1 | 1.5 | Done |
| 24/08 | Implement exercise availability & user constraints check | 1 | 1 | Done |
| 24/08 | Implement safety constraints check | 1 | 1 | Done |
| 25/08 | Implement `coach_retry_count` logic & pass/fail routing | 1 | | Todo |
| 25/08 | Implement `notify_fail` node (retry >= 3) | 0.5 | | Todo |
| 25/08 | Unit tests for deterministic verification rules | 0.5 | | Todo |

## Milestone 6 — HITL review gate (5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 25/08 | Implement `hitl_review` node (`interrupt()` approve/reject) | 1 | | Todo |
| 25/08 | Implement approve routing → end | 0.5 | | Todo |
| 25/08 | Implement reject + feedback routing → `coach_agent` revision | 1.5 | | Todo |
| 25/08 | Implement `hitl_rejected_no_feedback` node (stop immediately) | 0.5 | | Todo |
| 25/08 | Implement `hitl_exhausted` node (reject + retry >= 3) | 0.5 | | Todo |
| 25/08 | Implement `hitl_retry_count` tracking | 0.5 | | Todo |
| 25/08 | Integration test: full HITL approve/reject/exhausted loop | 0.5 | | Todo |

## Milestone 7 — QA agent & RAG pipeline (8h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 25/08 | Implement `qa_agent` node (LangGraph agent) + tools binding | 1 | | Todo |
| 25/08 | Implement `search_knowledge` tool (pgvector retrieval, `top_k=4`, cosine similarity) | 1 | | Todo |
| 26/08 | Implement `load_profile` tool for QA context | 0.5 | | Todo |
| 26/08 | Build embedding pipeline (`text-embedding-3-small`) for `knowledge_chunks` | 1 | | Todo |
| 26/08 | Implement similarity threshold filtering & duplicate/overlap removal | 1 | | Todo |
| 26/08 | Implement `ragas_verification` node (faithfulness scoring) | 1 | | Todo |
| 26/08 | Implement `qa_fallback` node (untrusted/insufficient-context response) | 1 | | Todo |
| 26/08 | Wire routing: `>= 0.9` pass / `< 0.9` retry / `< 0.9` & retry >= 3 fallback | 0.5 | | Todo |
| 26/08 | Unit tests for QA agent + RAG retrieval pipeline | 1 | | Todo |

## Milestone 8 — Memory & persistence (6h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 26/08 | Integrate `AsyncPostgresSaver` checkpointer + resume-after-interrupt tests | 1 | | Todo |
| 27/08 | Setup `PostgresStore` for preferences, accumulated knowledge, facts | 2 | | Todo |
| 27/08 | Create `knowledge_chunks` table + pgvector index | 1 | | Todo |
| 27/08 | Data migration scripts / seed nutrition & injury knowledge base | 1 | | Todo |
| 27/08 | Integration test: short-term (checkpoint) vs long-term memory separation | 1 | | Todo |

## Milestone 9 — Observability & error handling (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 27/08 | Integrate Langfuse tracing across nodes, agents, and tool calls | 1 | | Todo |
| 27/08 | Track `run_id`, `user_id`, `intent`, retry counts, verification & RAGAS results | 1 | | Todo |
| 27/08 | Implement centralized error handling (LLM/tool failure retry policy) | 1 | | Todo |
| 28/08 | Latency tracking & final result logging | 1 | | Todo |

## Milestone 10 — Integration testing, refactor & bug fixing (8h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | End-to-end test: full coaching flow (intent → context → plan → verify → HITL) | 3 | | Todo |
| 28/08 | End-to-end test: full QA flow (intent → retrieval → answer → RAGAS) | 3 | | Todo |
| 28/08 | Code review & cleanup | 2 | | Todo |
