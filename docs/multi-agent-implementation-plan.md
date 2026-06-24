# PT AI Core Deep Researcher — Multi-Agent Implementation Plan

---

## Target Architecture

```text id="multi_agent_arch_01"
User Query
    ↓
SUPERVISOR (STANDARD)
    ↓
PLANNING_AGENT (XHIGH)
    ↓
write_todos()
    ↓
RESEARCH_AGENT (STANDARD)
    ↓
FITNESS_REASONING_AGENT (STANDARD)
    ↓
VERIFICATION_AGENT (XHIGH)
    ↓
SUPERVISOR (STANDARD)
    ├── FIX_LOOP → FITNESS_REASONING_AGENT
    ├── REPLAN → PLANNING_AGENT
    ├── HITL → WAIT → SUPERVISOR
    └── COMPLETE
            ↓
     PERSIST_RESULTS()
            ↓
          RETURN
```

---

## Agent Responsibilities

| Agent | Tier | Creates Intelligence | VFS Outputs |
| --- | --- | --- | --- |
| `SupervisorAgent` | STANDARD | No — deterministic router | `logs/supervisor_decisions.jsonl` |
| `PlanningAgent` | XHIGH | Yes — domain check, profile extraction, plan, todos | `plan/plan.md`, `plan/todos.json`, `plan/profile.json` |
| `ResearchAgent` | STANDARD | Yes — evidence retrieval via MCP | `research/research_notes.md`, `research/sources.json` |
| `FitnessReasoningAgent` | STANDARD | Yes — macro targets, safety, plan synthesis | `fitness/calculations.json`, `fitness/final_plan.md` |
| `VerificationAgent` | XHIGH | Yes — programmatic + LLM verify, RAGAS | `verify/verification_vN.json`, `verify/ragas.json` |

### Non-Agent Components

| Component | Type | Purpose |
| --- | --- | --- |
| `HITL interrupt` | LangGraph interrupt | Pause for missing info, unsafe goals, approval, retry exhaustion |
| `PERSIST_RESULTS()` | Deterministic function | Write final artifact + run metadata after COMPLETE |

---

## LangGraph DCG

```text id="multi_agent_graph_01"
START
  ↓
SUPERVISOR_NODE
  ↓
PLANNING_NODE
  ↓
RESEARCH_NODE
  ↓
FITNESS_REASONING_NODE
  ↓
VERIFICATION_NODE
  ↓
SUPERVISOR_NODE
  ├── FIX_LOOP → FITNESS_REASONING_NODE → VERIFICATION_NODE
  ├── REPLAN → PLANNING_NODE → RESEARCH_NODE
  ├── HITL → WAIT → SUPERVISOR_NODE
  └── COMPLETE
        ↓
PERSIST_RESULTS()
        ↓
END
```

Supervisor routing is **rule-based** — reads structured JSON from VerificationAgent, no LLM call required for routing decisions.

---

## State Contract

```python id="multi_agent_state_01"
class AgentState(TypedDict):
    run_id: str
    thread_id: str
    query: str
    workspace_path: str
    current_node: str
    route_decision: str | None       # FIX_LOOP | REPLAN | HITL | COMPLETE
    retry_count: int
    replan_count: int
    missing_fields: list[str]
    waiting_for_user: bool
    approval_status: str | None
    verification_passed: bool
    faithfulness_score: float | None
    final_artifact_path: str | None
```

State must not store research notes, drafts, calculations, or verification reports — VFS only.

---

## VFS Workspace

```text id="multi_agent_vfs_01"
workspace/run_<id>/
├── plan/
│   ├── plan.md
│   ├── todos.json
│   └── profile.json
├── research/
│   ├── research_notes.md
│   ├── sources.json
│   └── findings.json
├── fitness/
│   ├── calculations.json
│   ├── safety_flags.json
│   └── final_plan.md
├── verify/
│   ├── verification_v1.json
│   └── ragas.json
├── final/
│   └── final_plan.md
└── logs/
    ├── supervisor_decisions.jsonl
    └── persist_result.json
```

Each agent writes only to its owned folder. `PERSIST_RESULTS()` copies `fitness/final_plan.md` → `final/final_plan.md` after COMPLETE.

---

## Reasoning Sandwich

Only 2 agents use XHIGH — where reasoning quality directly affects output.

| Agent | Tier | Why |
| --- | --- | --- |
| `PlanningAgent` | XHIGH | Strategic decomposition, domain judgment, profile gap analysis |
| `VerificationAgent` | XHIGH | Quality judgment, RAGAS interpretation, pass/fail reasoning |
| `SupervisorAgent` | STANDARD | Rule-based routing — reads structured verification JSON |
| `ResearchAgent` | STANDARD | Retrieval and summarization |
| `FitnessReasoningAgent` | STANDARD | Calculations and plan synthesis |

```text
XHIGH  → Planning (start) + Verification (end)
STANDARD → everything else
```

---

## Build-Verify-Fix Loop

```text id="multi_agent_bvf_01"
FITNESS_REASONING_AGENT builds plan
    ↓
VERIFICATION_AGENT verifies
    ↓
SUPERVISOR reads verification_vN.json
    ├── PASS + faithfulness >= 0.90 → HITL approval → COMPLETE
    ├── FIX_LOOP (retry_count < 3) → FITNESS_REASONING_AGENT
    ├── REPLAN (major issues) → PLANNING_AGENT
    └── HITL (exhausted retries / missing info / unsafe)
```

Verification includes:

* Schema validation
* Citation coverage
* Fitness safety check
* Profile ↔ calculation ↔ recommendation consistency
* RAGAS faithfulness (target >= 0.90)

---

## HITL Interrupt Points

Handled by Supervisor via LangGraph `interrupt()`, not a separate agent.

* Missing profile fields (detected by PlanningAgent)
* Ambiguous or conflicting goals
* Unsafe training constraints
* `retry_count >= 3` after FIX_LOOP
* Final approval before `PERSIST_RESULTS()`

---

## LangFuse Trace Hierarchy

```text id="langfuse_trace_01"
Thread: thread_id
└── Trace: run_id
    ├── Supervisor routing span (no LLM)
    ├── Planning agent span (XHIGH)
    ├── Research agent span + MCP tool spans
    ├── Fitness reasoning span
    ├── Verification agent span (XHIGH)
    ├── FIX_LOOP / REPLAN cycle spans (if any)
    ├── HITL interrupt span
    └── PERSIST_RESULTS span (no LLM)
```

---

## Implementation Pseudocode

```python id="multi_agent_pseudocode_01"
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", execute_supervisor)
    graph.add_node("planning", execute_planning_agent)
    graph.add_node("research", execute_research_agent)
    graph.add_node("fitness_reasoning", execute_fitness_reasoning_agent)
    graph.add_node("verification", execute_verification_agent)
    graph.add_node("hitl", execute_hitl_interrupt)
    graph.add_node("persist", persist_results)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor)
    graph.add_edge("planning", "research")
    graph.add_edge("research", "fitness_reasoning")
    graph.add_edge("fitness_reasoning", "verification")
    graph.add_edge("verification", "supervisor")
    graph.add_edge("hitl", "supervisor")
    graph.add_edge("persist", END)
    return graph.compile(checkpointer=checkpointer, interrupt_before=["hitl"])
```

```python id="multi_agent_supervisor_pseudocode_01"
def route_from_supervisor(state: AgentState) -> str:
    if state["waiting_for_user"]:
        return "hitl"
    if state["route_decision"] == "REPLAN":
        return "planning"
    if state["route_decision"] == "FIX_LOOP":
        return "fitness_reasoning"
    if state["route_decision"] == "COMPLETE":
        if state["approval_status"] != "approved":
            state["waiting_for_user"] = True
            return "hitl"
        return "persist"
    # Initial dispatch
    if state["current_node"] == "supervisor" and not state.get("plan_exists"):
        return "planning"
    return state["route_decision"]
```

```python id="persist_results_pseudocode_01"
def persist_results(state: AgentState) -> AgentState:
    vfs = VFS(state["workspace_path"])
    vfs.copy("fitness/final_plan.md", "final/final_plan.md")
    save_run_metadata(state)
    state["final_artifact_path"] = "final/final_plan.md"
    return state
```

---

## 2-Week Implementation Plan

### Week 1 — Core Agents

| Day | Task |
| --- | --- |
| 1 | `AgentState`, VFS interface, workspace schemas |
| 2 | Model-tier router, LangGraph checkpointer, graph skeleton |
| 3 | `PlanningAgent` — domain check, profile extraction, `write_todos`, HITL for missing fields |
| 4 | MCP client boundary + `ResearchAgent` |
| 5 | `FitnessReasoningAgent` — macro targets, safety, plan synthesis → `fitness/final_plan.md` |

### Week 2 — Verification, Routing, Release

| Day | Task |
| --- | --- |
| 6 | `VerificationAgent` — programmatic checks + LLM verify + RAGAS |
| 7 | `SupervisorAgent` — rule-based routing, BVF loop, retry/replan counters |
| 8 | HITL interrupts — clarification, approval, retry exhaustion |
| 9 | `PERSIST_RESULTS()` + crash-resume tests |
| 10 | LangFuse tracing — 5 agent spans + MCP + routing |
| 11 | Integration tests — happy paths + edge cases from `workflow.md` |
| 12 | RAGAS benchmark — macro calculation, training |
| 13 | Full acceptance suite |
| 14 | Review traces, VFS artifacts, freeze Phase 1 criteria |

---

## Acceptance Criteria

* Exactly 5 LLM agents — no orchestration-only agents
* `write_todos` runs before any MCP retrieval
* External data access only through MCP
* All reasoning artifacts in VFS, not state
* BVF loop blocks termination until verification passes
* RAGAS faithfulness >= 0.90
* HITL approval before `PERSIST_RESULTS()`
* LangGraph checkpointer resumes interrupted runs
* LangFuse trace shows 5 agent spans + routing + MCP calls
* Fitness domain guardrails reject out-of-scope requests

---
