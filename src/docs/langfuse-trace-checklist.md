# LangFuse Trace Checklist

Verify the trace tree in LangFuse UI (`LANGFUSE_HOST`, default `http://localhost:3000`) after a full happy-path run.

## Preconditions

- `.env` has `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- Run graph with `build_graph_invoke_config(state)` and `flush_langfuse()` after completion
- Session groups by `thread_id` (`langfuse_session_id` metadata)

## Expected hierarchy

```text
Thread: thread_id
└── Trace: run_id (deterministic trace id seeded from run_id)
    ├── Supervisor
    ├── Planning (reasoning_tier=XHIGH)
    ├── Research
    │   ├── tavily-search
    │   └── tavily-extract
    ├── Fitness
    ├── Verification (reasoning_tier=XHIGH)
    ├── partial_rerun_FIX_REASONING | partial_rerun_REPLAN | partial_rerun_RERESEARCH (on failure loops only)
    ├── HITL
    └── PERSIST_RESULTS
```

## Manual verification steps

1. Start a run with a complete profile and approve at HITL.
2. Open LangFuse → Traces → filter by tag `pt-ai-core` or session `thread_id`.
3. Confirm root trace name/input includes the user query.
4. Confirm child spans appear in execution order for a happy path:
   - Supervisor → Planning → Supervisor → Research → (tavily-search/extract) → Supervisor → Fitness → Verification → Supervisor → HITL → Supervisor → PERSIST_RESULTS
5. Trigger a verification failure (e.g. remove sources) and confirm a `partial_rerun_*` span appears on the next affected subgraph.
6. Confirm `persist` span metadata includes `subgraph=persist` and final artifact path in node output.

## Automated coverage

- `tests/test_langfuse_spans.py` — span naming and wrapper wiring
- `tests/integration/` — todos gate, Tavily path, partial rerun routing, happy path
- `tests/test_ragas_benchmark.py` — golden faithfulness regression (≥ 0.90)
