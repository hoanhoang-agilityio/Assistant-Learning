# Task Design — PT AI Core Deep Researcher

Formal task contract for the supervisor-orchestrated pipeline. Maps 1:1 to runtime code in `src/core/graph/`.

**Convention:** `@entrypoint` = single run bootstrap + graph invoke. `@task` = top-level LangGraph node invoked by the supervisor router.

---

## @entrypoint

```python
@entrypoint
def start_run(
    *,
    query: str,
    user_profile: dict | None = None,
    constraints: dict | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> RunStatus:
    """
    Bootstrap a run, invoke the compiled LangGraph, return lifecycle status.

    API surface : POST /runs  →  RunOrchestrator.start_run()
    State boot  : create_initial_state()  →  OrchestrationState
    Graph       : build_graph().invoke(state, config)
    Resume      : POST /runs/{run_id}/resume  →  Command(update=...)
    """
```

| Field | Type | Source |
| --- | --- | --- |
| `query` | `str` (min 3) | `CreateRunRequest.query` |
| `user_profile` | `dict` | age, sex, height, weight, goal, … |
| `constraints` | `dict` | days_per_week, equipment, … |
| `run_id` | `str` | auto `run_{uuid[:10]}` if omitted |
| `user_id` | `str` | `X-User-Id` header or request body |

**Output:** `RunStatus` — `status`, `current_node`, `waiting_for_user`, `faithfulness_score`, `final_artifact_path`, `steps`, `error_message`.

**Graph flow after entrypoint:**

```text
START → supervisor → [planning | research | fitness | verification | hitl | persist] → supervisor → … → END
```

**Implementation:** `src/core/graph/service.py`, `src/core/graph/run.py`, `src/api/routes/runs.py`

---

## @task Signatures

| # | Task | Signature | Tier | VFS output |
| --- | --- | --- | --- | --- |
| 1 | **planning** | `invoke_planning_subgraph(state: OrchestrationState) -> dict` | XHIGH | `plan/plan.md`, `plan/todos.json`, `plan/profile.json` |
| 2 | **research** | `invoke_research_subgraph(state: OrchestrationState) -> dict` | STANDARD | `research/sources.json`, `research/findings.json`, `research/research_notes.md` |
| 3 | **fitness** | `invoke_fitness_subgraph(state: OrchestrationState) -> dict` | STANDARD | `fitness/calculations.json`, `fitness/final_plan.md`, `fitness/workout.json` |
| 4 | **verification** | `invoke_verification_subgraph(state: OrchestrationState) -> dict` | XHIGH | `verify/verification_v1.json`, `verify/ragas.json` |
| 5 | **hitl** | `invoke_hitl_node(state: OrchestrationState) -> dict` | — | — (interrupt only) |
| 6 | **persist** | `invoke_persist_node(state: OrchestrationState) -> dict` | — | `final/final_plan.md`, `logs/persist_result.json` |

**Orchestrator (not a @task):** `supervisor_node(state: OrchestrationState) -> dict` — classifies request, reads verification report, sets `route_decision`, never produces fitness content.

---

## Task Contracts (detail)

### @task 1 — planning

```python
@task("planning")
def invoke_planning_subgraph(state: OrchestrationState) -> dict:
    """
    Extract/validate profile, generate ExecutionPlan (3–10 research tasks), write todos.

    Preconditions : supervisor routed to planning; plan/profile.json already complete/valid
    Postconditions: plan/* on VFS (execution_plan.json, plan.md, and a re-persisted
                    profile.json enriched with goal-spec fields -- see the VFS-profile plan)
    HITL trigger  : missing_fields → waiting_for_user=True (raised by the User subgraph,
                    not Planning -- see route_from_supervisor's profile gate)
    """
```

Profile extraction/validation is owned by the **User subgraph**, not Planning (see `agents/planning-subgraph.md`'s staleness note) — Planning trusts `plan/profile.json` is already complete/valid by the time it runs, gated by `route_from_supervisor`'s profile check.

| Internal steps | `generate_plan` \| `reuse_execution_plan` (entry decided by `_route_entry`) |
| Key tools | `load_run_profile` (VFS), `generate_plan` |
| State in | `query`, `request_type`, `workspace_path`, `route_decision`, `revision_feedback` |
| State out | `current_node="planning"` (profile fields are not read from or written to `OrchestrationState` — see `plan/profile.json` on VFS) |

**File:** `src/core/subgraphs/planning/graph.py`

---

### @task 2 — research

```python
@task("research")
def invoke_research_subgraph(state: OrchestrationState) -> dict:
    """
    Gate on todos, run research agent, retrieve/rank/verify evidence, write artifacts.

    Preconditions : plan/todos.json exists (todos gate)
    Postconditions: research/* on VFS
    Blocked path  : blocked_by_todos → waiting_for_user=True
    """
```

| Internal steps | `todos_gate` → `research_agent` → `write_artifacts` |
| Key tools | `search_evidence`, `retrieve_documents`, `rank_sources`, `verify_sources` (Tavily MCP) |
| State in | `workspace_path`, execution plan from VFS |
| State out | `current_node="research"`, `waiting_for_user?` |

**File:** `src/core/subgraphs/research/graph.py`

---

### @task 3 — fitness

```python
@task("fitness")
def invoke_fitness_subgraph(state: OrchestrationState) -> dict:
    """
    Calculate macros, build training plan, synthesize draft, safety check.

    Preconditions : research artifacts available (or FIX_REASONING rerun with feedback)
    Postconditions: fitness/* on VFS including final_plan.md
    Auto-edge     : fitness → verification (no supervisor hop)
    """
```

| Internal steps | `load_context` → `build_blueprint` → `calculate_macros` → `resolve_workout_template` → `fitness_planner` → `safety_check` → `synthesize_plan` → `write_artifacts` |
| Key tools | `calculate_macros`, `build_training_plan`, `synthesize_plan` |
| State in | `workspace_path`, `days_per_week_explicit`, `route_decision` (FIX_REASONING feeds verification_feedback) — `profile`/`constraints` are loaded from `plan/profile.json` inside `load_context`, not read from `OrchestrationState` |
| State out | `current_node="fitness"` |

**File:** `src/core/subgraphs/fitness/graph.py`

---

### @task 4 — verification

```python
@task("verification")
def invoke_verification_subgraph(state: OrchestrationState) -> dict:
    """
    Citation, consistency, safety checks + RAGAS faithfulness. Supervisor reads report next.

    Preconditions : fitness/final_plan.md exists
    Postconditions: verify/* on VFS; verification_passed + faithfulness_score on orchestration state
    """
```

| Internal steps | `load_context` → `citation_check` → `consistency_check` → `safety_check` → `ragas_faithfulness` → `write_artifacts` |
| Key tools | `citation_check`, `consistency_check`, `safety_check`, `ragas_faithfulness` |
| State in | `workspace_path` |
| State out | `current_node="verification"`, `verification_passed`, `faithfulness_score` |
| Pass threshold | faithfulness ≥ 0.90 (`FAITHFULNESS_PASS_THRESHOLD`) |

**File:** `src/core/subgraphs/verification/graph.py`

---

### @task 5 — hitl

```python
@task("hitl")
def invoke_hitl_node(state: OrchestrationState) -> dict:
    """
    Human-in-the-loop interrupt: clarification (missing profile) or final approval.

    Interrupt     : graph compiled with interrupt_before=["hitl"]
    Resume        : POST /runs/{run_id}/resume with approval_status / decision_type
    """
```

| Modes | `request_clarification` (missing_fields) \| `request_approval` (COMPLETE / verification passed) |
| State in | `waiting_for_user`, `approval_status`, `user_response`, `route_decision` |
| State out | `current_node="hitl"`, `waiting_for_user`, `approval_status`, `hitl_type`, `hitl_message` |
| On approve | `approval_status="approved"` → supervisor routes to persist |
| On reject | `approval_status="rejected"` → END |
| On revision | `revision_requested` → REPLAN → planning |

**File:** `src/core/hitl/node.py`

---

### @task 6 — persist

```python
@task("persist")
def invoke_persist_node(state: OrchestrationState) -> dict:
    """
    Deterministic final write after COMPLETE + approval guards pass.

    Guards        : verification_passed, faithfulness ≥ 0.90, approval_status == approved
    Postconditions: final/* artifacts, logs/persist_result.json, final_artifact_path set
    """
```

| Internal steps | `save_run` → `save_metrics` → `save_artifacts` |
| Key tools | `save_run`, `save_metrics`, `save_artifacts` |
| State in | full `OrchestrationState` snapshot |
| State out | `current_node="persist"`, `final_artifact_path`, `waiting_for_user=False` |
| Blocked path | `persist_trigger_blocked` → waiting_for_user=True |

**File:** `src/core/persist/node.py`

---

## Supervisor Routing (between @tasks)

`route_from_supervisor(state)` in `src/core/graph/routing.py`:

| `route_decision` | Condition | Next @task |
| --- | --- | --- |
| *(default pipeline)* | `affected_domains` order | planning → research → fitness → verification → hitl |
| `FIX_REASONING` | minor issues, `retry_count < 2` | fitness → verification |
| `REPLAN` | structural issues, `replan_count ≤ 1` | planning → … |
| `RERESEARCH` | weak evidence, `retry_count < 2` | research → fitness → verification |
| `HITL` | exhausted retries / unsafe / missing info | hitl |
| `COMPLETE` | verify pass + faithfulness ≥ 0.90 | hitl (approval) → persist |

**Budgets** (`src/core/agents/rerun.py`):

| Counter | Max | Effect when exceeded |
| --- | --- | --- |
| `retry_count` | 2 | Route to HITL |
| `replan_count` | 1 | Route to HITL or END |

---

## Error Handling Strategy (try/except per @task)

| Layer | Pattern | Behavior |
| --- | --- | --- |
| **@entrypoint** | `try/except Exception` in `_execute_create_run`, `_execute_resume_run`, `_execute_continue_run` | Log exception, store `_run_failures[run_id]`, expose `error_message` in `RunStatus` |
| **@task nodes** | No per-task try/except wrapper | Uncaught exceptions bubble to entrypoint; checkpoint preserves last good state |
| **LLM (XHIGH)** | Transient error → Anthropic fallback; non-transient → raise | `invoke_xhigh_structured_output()` in `src/core/llm/factory.py` |
| **LLM (STANDARD)** | Provider invoke; rate limiter records usage | `invoke_standard_structured_output()` |
| **Tavily MCP** | JSON parse fallback; `RuntimeError` on MCP connection failure | `src/core/mcp/tavily_client.py` — no exponential backoff |
| **RAGAS** | Deterministic heuristic; **no retry** | `heuristic_faithfulness_data()` — single pass |
| **HITL** | Guard checks before persist; blocked persist returns state update, not exception | `persist_trigger_data()` |
| **VFS** | Path-safe reads; missing file → empty default in node logic | Per subgraph `load_context` nodes |

---

## Retry Approach

| Subsystem | Strategy | Config / limit |
| --- | --- | --- |
| **Tavily search** | Iteration cap inside research agent | `research_max_search_iterations=2`, `research_max_total_searches=3` |
| **Tavily extract** | Top-K cap | `research_max_total_extracts=5` |
| **Tavily backoff** | None implemented | Fail fast; supervisor may trigger `RERESEARCH` (max 2) |
| **LLM fallback** | OpenAI → Anthropic on transient XHIGH errors only | `src/core/llm/factory.py` |
| **Fitness planner** | In-subgraph retry with feedback | `max_planner_attempts=2`; `fix_reasoning_planner_attempts=1` |
| **Partial rerun** | Supervisor-driven FIX_REASONING / REPLAN / RERESEARCH | `MAX_RETRY_COUNT=2`, `MAX_REPLAN_COUNT=1` |
| **RAGAS** | **No retry** | Single evaluation; failure → partial rerun or HITL |

---

## Data Flywheel — Failure Trace Requirements

Every failed or retried run MUST leave enough trace for post-mortem and quality iteration.

| Artifact | Path | When written |
| --- | --- | --- |
| Supervisor decisions | `logs/supervisor_decisions.jsonl` | After verification fail → rerun decision |
| Verification report | `verify/verification_v1.json` | Every verification @task run |
| RAGAS scores | `verify/ragas.json` | Every verification @task run |
| Pipeline cost | `logs/pipeline_cost.json` | Run end (success or failure) |
| Persist result | `logs/persist_result.json` | Successful persist @task |
| LangFuse trace | external | Full hierarchy: supervisor → subgraph → Tavily MCP → HITL → persist |
| API failure | `RunOrchestrator._run_failures` | Uncaught exception at @entrypoint |

**Minimum fields for failure analysis:**

```json
{
  "run_id": "...",
  "thread_id": "...",
  "route_decision": "RERESEARCH",
  "retry_count": 1,
  "replan_count": 0,
  "verification_passed": false,
  "faithfulness_score": 0.82,
  "feedback": "...",
  "error": "optional entrypoint exception message"
}
```

---

## OrchestrationState (shared across all @tasks)

```python
class OrchestrationState(TypedDict):
    run_id: str
    thread_id: str
    user_id: str
    current_node: str
    query: str
    profile_complete: bool
    profile_valid: bool
    days_per_week_explicit: bool
    request_type: RequestType | None
    affected_domains: list[AffectedDomain]
    route_decision: RouteDecision | None   # FIX_REASONING | REPLAN | RERESEARCH | HITL | COMPLETE
    retry_count: int
    replan_count: int
    verification_passed: bool
    faithfulness_score: float | None
    waiting_for_user: bool
    approval_status: ApprovalStatus | None
    user_response: str | None
    revision_feedback: str | None
    workspace_path: str
    final_artifact_path: str | None
    refusal_message: str | None
    steps: list[str]
```

**Source:** `src/core/agents/state.py`

**Note:** `user_profile`/`constraints` were removed (moved to VFS `plan/profile.json`, seeded via `core/profile/store.py:seed_profile` at create-run time and owned by the User subgraph) and `approved_tools`/`pending_tool` were removed (unused per-tool HITL-approval scaffolding with no real caller) — see `docs/reports/orchestration_profile_vfs_plan.md`. The `@entrypoint`/`start_run` API surface above is unaffected: `user_profile`/`constraints` are still accepted as request parameters, just no longer stored on `OrchestrationState`.

---

## Related Docs

| Doc | Scope |
| --- | --- |
| `multi-agent-implementation-plan.md` | Architecture diagram |
| `implementation-specification.md` | Full spec (tools, VFS, routing) |
| `agents/supervisor.md` | Supervisor tools and rerun logic |
| `agents/planning-subgraph.md` | Planning internals |
| `agents/research-subgraph.md` | Research + Tavily MCP |
| `agents/fitness-subgraph.md` | Fitness synthesis |
| `agents/verification-subgraph.md` | Verification + RAGAS |
