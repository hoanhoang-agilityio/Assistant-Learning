# Phase 1 — Implementation Schedule (2 Weeks)

Detailed task estimates for the Core Deep Researcher (Fitness AI).

## Assumptions

| Parameter | Value |
| --- | --- |
| Capacity | **8 hours / day** |
| Work week | **5 days / week** |
| Total duration | **2 weeks · 10 working days · 80 hours** |
| Scope | Full Phase 1: graph, subgraphs, **Tavily MCP (pre-built)**, HITL, persist, **FastAPI**, **Streamlit**, **full LangFuse tracing**, **RAGAS benchmark**, tests, acceptance |
| Reference docs | `implementation-specification.md`, `multi-agent-implementation-plan.md` |

## Progress Snapshot (as of scaffold + state/tools PRs)

| Area | Status |
| --- | --- |
| Module scaffold (supervisor + 4 subgraphs) | Done |
| `OrchestrationState` + subgraph `TypedDict` schemas | Done |
| Supervisor / HITL / persist / subgraph tool stubs | Done (bodies are `...`) |
| `Settings` (Postgres DSN, workspace root, LLM keys, LangFuse) | Done |
| `docker-compose.yml` (Postgres 16) | Done |
| Tavily MCP client wiring (pre-built server, no custom MCP) | Not started |
| VFS module | Not started |
| LangGraph `StateGraph` + checkpointer | Not started |
| Subgraph graphs + real tool logic | Not started |
| HITL interrupt + resume | Not started |
| LangFuse full span hierarchy | Not started |
| FastAPI + Streamlit UI | Not started |
| RAGAS benchmark script | Not started |
| Integration / acceptance tests | Not started |

---

## Week 1 — Foundation & Intelligence Subgraphs

**Goal:** Runnable supervisor graph; Tavily-backed research ready; all four subgraphs produce VFS artifacts on the happy path.

---

### Day 1 — VFS & Run Bootstrap (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.0h | Design `VFS` interface (`read`, `write`, `exists`, `append`) | `core/vfs/vfs.py` |
| 1.5h | Path-safe VFS rooted at `settings.workspace_root` | `core/vfs/vfs.py` |
| 1.0h | `init_run_workspace(run_id)` — `workspace/run_<id>/` folder tree | `core/vfs/bootstrap.py` |
| 1.0h | `create_initial_state()` — set `workspace_path` on `OrchestrationState` | `core/graph/run.py` |
| 2.0h | Unit tests: write/read, nested paths, `exists`, `append` | `tests/test_vfs.py` |

**Exit criteria:** Workspace folders created per run; VFS tests pass.

**PR:** `feat/vfs-workspace`

---

### Day 2 — Supervisor LangGraph + Checkpointer (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.5h | Postgres checkpointer factory | `core/graph/checkpointer.py` |
| 2.0h | `StateGraph` — nodes: supervisor, planning, research, fitness, verification, hitl, persist | `core/graph/builder.py` |
| 1.5h | `route_from_supervisor()` conditional edges | `core/graph/routing.py` |
| 2.0h | Implement `read_global_state`, `classify_request`, `route_subgraph` (rule-based) | `core/agents/tools.py` |
| 1.0h | `supervisor_node` — update `current_node`, `route_decision` | `core/agents/supervisor.py` |

**Exit criteria:** Graph compiles; first invoke routes to `planning`.

**PR:** `feat/supervisor-graph`

---

### Day 3 — Planning Subgraph (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.0h | Planning `StateGraph` as compiled subgraph node | `core/subgraphs/planning/graph.py` |
| 2.0h | `extract_profile` — merge query + profile + constraints | `core/subgraphs/planning/tools.py` |
| 1.5h | `validate_profile` — required fields, `missing_fields` | `core/subgraphs/planning/tools.py` |
| 2.5h | `write_todos` — todos + VFS writes (`plan/todos.json`, `plan/profile.json`) | `core/subgraphs/planning/tools.py` |
| 1.0h | Planning agent node + test (`missing_fields` → HITL flag) | `agent.py`, `tests/test_planning_subgraph.py` |

**Exit criteria:** `plan/todos.json` on VFS before research can run.

**PR:** `feat/planning-subgraph`

---

## Research Retrieval Architecture

External evidence via official [Tavily MCP server](https://docs.tavily.com/documentation/mcp) only.

| Layer | Module | Role |
| --- | --- | --- |
| Tavily MCP | `core/mcp/tavily_client.py` | Wire **pre-built** Tavily MCP via `langchain-mcp-adapters` |
| Research tools | `search_evidence`, `retrieve_documents`, `rank_sources`, `verify_sources` | Tavily-backed retrieval; todos gate enforced |

### Tavily MCP (pre-built — no custom server)

| Item | Detail |
| --- | --- |
| Server | Official **Tavily MCP** — remote `https://mcp.tavily.com/mcp` (streamable HTTP) or local `npx -y tavily-mcp@latest` (stdio) |
| Client | `langchain-mcp-adapters` `MultiServerMCPClient` — config + tool binding only |
| Auth | `TAVILY_API_KEY` in `Settings` / `.env` |
| Tool mapping | `search_evidence` → `tavily-search`; `retrieve_documents` → `tavily-extract` |
| Out of scope | Custom MCP server, MCP protocol implementation, new research API wrappers |

---

### Day 4 — Research Subgraph + Tavily MCP (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 0.5h | Extend `Settings`: **`tavily_api_key`** | `core/config/settings.py` |
| 1.5h | **Tavily MCP client** — `MultiServerMCPClient` → official Tavily MCP; smoke test `tavily-search` / `tavily-extract`; **no custom MCP build** | `core/mcp/tavily_client.py` |
| 1.0h | Research `StateGraph` subgraph node | `core/subgraphs/research/graph.py` |
| 2.5h | `search_evidence` + `retrieve_documents` — delegate to Tavily MCP tools; **`todos` gate** | `core/subgraphs/research/tools.py` |
| 2.0h | `rank_sources` + `verify_sources` | `core/subgraphs/research/tools.py` |
| 1.0h | VFS writes (`research/sources.json`, `research/findings.json`) + subgraph test | `research/*`, `tests/test_research_subgraph.py` |

**Exit criteria:** Research blocked without todos; Tavily MCP connected via pre-built server; evidence artifacts on VFS.

**PR:** `feat/research-subgraph`

---

### Day 5 — Fitness Subgraph (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.0h | Fitness `StateGraph`; parent edge `fitness → verification` | `core/subgraphs/fitness/graph.py` |
| 2.0h | `calculate_macros` | `core/subgraphs/fitness/tools.py` |
| 2.5h | `build_training_plan` | `core/subgraphs/fitness/tools.py` |
| 2.0h | `synthesize_plan` + VFS (`fitness/calculations.json`, `fitness/final_plan.md`) | `core/subgraphs/fitness/tools.py` |
| 0.5h | `safety_flags` for extreme volume / macros | `core/subgraphs/fitness/tools.py` |

**Exit criteria:** `fitness/final_plan.md` on VFS; `draft_plan` ready for verification.

**PR:** `feat/fitness-subgraph`

---

## Week 2 — Verification, Control Flow, Observability & Delivery

**Goal:** Full pipeline loop, LangFuse tracing, RAGAS benchmark, API/UI, and acceptance.

---

### Day 6 — Verification Subgraph + RAGAS Tool (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.0h | Verification `StateGraph` subgraph node | `core/subgraphs/verification/graph.py` |
| 1.5h | `citation_check` | `core/subgraphs/verification/tools.py` |
| 1.5h | `consistency_check` | `core/subgraphs/verification/tools.py` |
| 1.5h | `safety_check` | `core/subgraphs/verification/tools.py` |
| 2.0h | `ragas_faithfulness` — set `faithfulness_score`, `pass_fail` | `core/subgraphs/verification/tools.py` |
| 0.5h | VFS: `verify/verification_v1.json`, `verify/ragas.json` | VFS writes |

**Exit criteria:** Structured verification report returned to supervisor.

**PR:** `feat/verification-subgraph`

---

### Day 7 — Partial Rerun + HITL (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 2.0h | `partial_rerun_decision` — FIX_REASONING / REPLAN / RERESEARCH | `core/agents/tools.py` |
| 1.5h | `retry_count` + `replan_count` guards in routing | `core/graph/routing.py` |
| 1.0h | Supervisor decision log → `logs/supervisor_decisions.jsonl` | `core/agents/supervisor.py` |
| 1.5h | HITL node + `interrupt_before=["hitl"]` | `core/graph/builder.py` |
| 1.0h | `request_clarification` + `request_approval` | `core/hitl/tools.py` |
| 1.0h | `hitl_control` + resume test | `core/agents/tools.py`, `tests/test_hitl_resume.py` |

**Exit criteria:** All rerun routes work; graph pauses and resumes at HITL.

**PR:** `feat/rerun-and-hitl`

---

### Day 8 — Persist, E2E & LangFuse Foundation (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 1.0h | `persist_trigger` guards (verify pass, score ≥ 0.90, approved) | `core/agents/tools.py` |
| 1.5h | `save_run` + `save_metrics` + `save_artifacts` | `core/persist/tools.py` |
| 2.0h | E2E test: START → … → HITL → persist → END (mocked LLM / Tavily) | `tests/test_e2e_happy_path.py` |
| 1.0h | Test fixtures: temp workspace + checkpointer | `tests/conftest.py` |
| 1.5h | LangFuse client from `settings.langfuse_*`; root trace per `run_id` | `core/observability/langfuse.py` |
| 1.0h | Supervisor span + thread (`thread_id`) wiring | callback handler |

**Exit criteria:** Happy path completes; root LangFuse trace created per run.

**PR:** `feat/persist-results`

---

### Day 9 — Full LangFuse, Integration Tests & RAGAS Benchmark (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 2.5h | **Full LangFuse span hierarchy** per spec: Planning, Research (+ **Tavily MCP** child spans), Fitness, Verification, partial rerun spans, HITL, PERSIST | `core/observability/langfuse.py` |
| 0.5h | Verify trace tree in LangFuse UI matches `multi-agent-implementation-plan.md` diagram | trace checklist |
| 2.0h | Integration tests: `write_todos` gate, Tavily research path, partial rerun, happy path (mocked) | `tests/integration/` |
| 2.0h | **`scripts/ragas_benchmark.py`** — batch N sample queries, aggregate faithfulness scores, CSV/JSON report | `scripts/ragas_benchmark.py` |
| 1.0h | Golden fixtures + CI regression: assert faithfulness ≥ 0.90 | `tests/test_ragas_benchmark.py` |

**Exit criteria:** Full trace hierarchy visible in LangFuse; benchmark script runs at scale; golden set passes.

**PR:** `feat/langfuse-and-ragas-benchmark`

---

### Day 10 — FastAPI, Streamlit UI & Acceptance (8h)

| Time | Task | Deliverable |
| --- | --- | --- |
| 2.0h | **FastAPI** — `POST /runs`, `GET /runs/{run_id}`, `POST /runs/{run_id}/resume` (HITL) | `src/api/main.py`, `src/api/routes/runs.py` |
| 0.5h | API smoke tests with `httpx` | `tests/test_api.py` |
| 2.5h | **Streamlit UI** — submit query, poll run status, HITL clarification/approval form, show final artifact | `src/ui/app.py` |
| 1.0h | Wire UI to FastAPI; document `uvicorn` + `streamlit run` in README | `README.md` |
| 1.0h | Walk acceptance criteria checklist (below) + manual demo | signed checklist |
| 1.0h | Fix P1 bugs; Ruff cleanup; final MR `feat/phase-1` → `main` | merge-ready |

**Exit criteria:** Run lifecycle works via API and Streamlit; all acceptance criteria met.

**PR:** `feat/api-and-streamlit-ui`

---

## Acceptance Criteria Checklist

Use on **Day 10** to confirm Phase 1 completion.

- [ ] Supervisor orchestrates via global state; subgraphs use scoped state
- [ ] Partial rerun: FIX_REASONING, REPLAN, RERESEARCH route to correct subgraph only
- [ ] `write_todos` enforced before Tavily retrieval
- [ ] **Official Tavily MCP server** (remote or `tavily-mcp` npx) — **no custom MCP server built**
- [ ] `search_evidence` / `retrieve_documents` map to `tavily-search` / `tavily-extract`
- [ ] External data access via Tavily MCP only
- [ ] Artifacts in VFS, not global state
- [ ] RAGAS faithfulness ≥ 0.90 on golden set
- [ ] **`scripts/ragas_benchmark.py` runs N queries and produces reproducible report**
- [ ] HITL approval before persist
- [ ] LangGraph checkpointer resume after interrupt
- [ ] **LangFuse trace hierarchy: supervisor → subgraphs → Tavily MCP → HITL → persist (+ rerun spans)**
- [ ] **FastAPI: create run, get status, resume HITL**
- [ ] **Streamlit: submit run, approve/reject, view final plan**
- [ ] Product scope: training + macro only

---

## Summary

| Week | Days | Focus | Hours |
| --- | --- | --- | --- |
| 1 | 1–5 | VFS, supervisor, planning, **research (Tavily MCP)**, fitness | 40h |
| 2 | 6–10 | Verification, rerun, HITL, persist, LangFuse, RAGAS benchmark, API, UI, acceptance | 40h |
| **Total** | **10** | | **80h** |

## PR Sequence

1. `feat/vfs-workspace`
2. `feat/supervisor-graph`
3. `feat/planning-subgraph`
4. `feat/research-subgraph`
5. `feat/fitness-subgraph`
6. `feat/verification-subgraph`
7. `feat/rerun-and-hitl`
8. `feat/persist-results`
9. `feat/langfuse-and-ragas-benchmark`
10. `feat/api-and-streamlit-ui`

## LangFuse Trace Hierarchy (Day 9 target)

```text
Thread: thread_id
└── Trace: run_id
    ├── Supervisor span (orchestration tools)
    ├── Planning subgraph span (XHIGH)
    ├── Research subgraph span
    │   └── Tavily MCP child spans (tavily-search, tavily-extract)
    ├── Fitness subgraph span
    ├── Verification subgraph span (XHIGH)
    ├── Partial rerun spans (FIX_REASONING / REPLAN / RERESEARCH)
    ├── HITL subsystem span
    └── PERSIST_RESULTS span
```
