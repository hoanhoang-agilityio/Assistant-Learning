# LangFuse Trace Checklist

Verify the trace tree in LangFuse UI (`LANGFUSE_HOST`, default `http://localhost:3000`) after a full happy-path run.

**Hierarchy reference:** [langfuse-hierarchy.md](./langfuse-hierarchy.md) — Runs → Traces → Threads (Sessions).  
**Code:** `src/core/observability/hierarchy.py`, `src/core/observability/langfuse.py`.

## Preconditions

- `.env` has `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` / `LANGFUSE_BASE_URL`
- Run graph with `build_graph_invoke_config(state)` and `flush_langfuse()` after completion
- Session (Thread) grouping: `session_id == thread_id` via `propagate_attributes` + `langfuse_session_id` metadata
- Trace (Run): deterministic `trace_id` seeded from `run_id`

## Expected hierarchy

```text
Thread / Session: thread_id
└── Trace: run_id (deterministic trace id seeded from run_id)
    ├── Supervisor
    ├── Planning (reasoning_tier=XHIGH)
    ├── Research
    │   ├── tavily_search
    │   └── tavily_extract
    ├── Fitness
    ├── Verification (reasoning_tier=XHIGH)
    ├── partial_rerun_FIX_REASONING | partial_rerun_REPLAN | partial_rerun_RERESEARCH (on failure loops only)
    ├── HITL
    └── PERSIST_RESULTS
```

## Manual verification steps

1. Start a run with a complete profile and approve at HITL.
2. Open LangFuse → **Sessions** → open `thread_id` (or Traces → filter by tag `pt-ai-core` / session `thread_id`).
3. Confirm the Session lists the run’s Trace; root trace input includes the user query.
4. Confirm child spans appear in execution order for a happy path:
   - Supervisor → Planning → Supervisor → Research → (tavily_search/extract when agent calls MCP) → Supervisor → Fitness → Verification → Supervisor → HITL → Supervisor → PERSIST_RESULTS
5. Trigger a verification failure (e.g. remove sources) and confirm a `partial_rerun_*` span appears on the next affected subgraph.
6. Confirm `persist` span metadata includes `subgraph=persist` and final artifact path in node output.
7. Optional: `fetch_langfuse_thread(thread_id)` returns the Session payload from `GET /api/public/sessions/{sessionId}`.

## Automated coverage

- `tests/test_langfuse_hierarchy_mapping.py` — Run/Trace/Thread id mapping + Sessions API helper
- `tests/test_langfuse_spans.py` — span naming and wrapper wiring
- `tests/integration/test_langfuse_hierarchy.py` — subgraph + Tavily MCP span recording
- `tests/integration/` — todos gate, Tavily path, partial rerun routing, happy path
- `tests/test_ragas_benchmark.py` — golden faithfulness regression (≥ 0.90)
