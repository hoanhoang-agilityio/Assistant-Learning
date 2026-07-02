# THE CORE DEEP RESEARCHER (FITNESS AI)

## Phase 1 — Full Implementation Specification

---

# 1. System Overview

The Core Deep Researcher is a **Fitness Training & Macro System**.

It transforms user fitness goals into:

* Evidence-based training plans
* Macro targets (calories, protein, carbs, fat)
* Verified actionable outputs

Architecture: **Supervisor-orchestrated subgraph DCG** with separated orchestration state and subgraph-scoped state. Product scope: training + macro only.

---

## NOT A GENERAL AI SYSTEM

The system does NOT support:

* Programming, finance, legal, medical diagnosis
* Meal planning, nutrition coaching, diet plans
* Supplement research

---

# 2. Runtime Contract

## Input

```json id="input_01"
{
  "run_id": "uuid",
  "thread_id": "uuid",
  "query": "I want to lose weight",
  "user_profile": {},
  "constraints": {}
}
```

## Output

```json id="output_01"
{
  "run_id": "...",
  "status": "completed",
  "artifact_path": "workspace/run_xxx/final/final_plan.md",
  "verification_passed": true,
  "approval_status": "approved",
  "faithfulness_score": 0.94
}
```

---

# 3. Graph Architecture

```text id="graph_01"
START
  ↓
SUPERVISOR (ORCHESTRATOR)
  ↓
PLANNING SUBGRAPH → RESEARCH SUBGRAPH → FITNESS SUBGRAPH → VERIFICATION SUBGRAPH
  ↓
SUPERVISOR
  ├── FIX_REASONING → FITNESS → VERIFICATION
  ├── REPLAN        → PLANNING
  ├── RERESEARCH    → RESEARCH → FITNESS → VERIFICATION
  ├── HITL          → WAIT → SUPERVISOR
  └── COMPLETE      → PERSIST_RESULTS → END
```

See `docs/multi-agent-implementation-plan.md` for full diagram.

---

# 4. State Architecture

## Orchestration State (Global)

LangGraph checkpointer stores this. Subgraph artifact content lives in VFS only.

```python id="state_01"
class OrchestrationState(TypedDict):
    run_id: str
    thread_id: str
    current_node: str

    query: str
    user_profile: dict
    constraints: dict

    request_type: str | None
    affected_domains: list[str]

    route_decision: str | None    # FIX_REASONING | REPLAN | RERESEARCH | HITL | COMPLETE
    retry_count: int
    replan_count: int

    verification_passed: bool
    faithfulness_score: float | None

    waiting_for_user: bool
    approval_status: str | None
    user_response: str | None

    workspace_path: str
    final_artifact_path: str | None
```

## Subgraph States (Scoped)

```python id="planning_state"
class PlanningState(TypedDict):
    profile: dict
    missing_fields: list[str]
    todos: list[str]
    planning_output: str | None
```

```python id="research_state"
class ResearchState(TypedDict):
    research_questions: list[str]
    evidence: list[dict]
    sources: list[dict]
    evidence_summary: str | None
```

```python id="fitness_state"
class FitnessState(TypedDict):
    macro_targets: dict
    training_constraints: dict
    training_plan: dict | None
    draft_plan: str | None
    safety_flags: list[str]
```

```python id="verification_state"
class VerificationState(TypedDict):
    verification_report: dict
    feedback: str | None
    faithfulness_score: float | None
    pass_fail: bool
```

---

# 5. Workspace (VFS)

```text id="vfs_01"
workspace/run_<id>/
├── plan/
├── research/
├── fitness/
├── verify/
├── final/
└── logs/
```

| Subgraph | VFS folder |
| --- | --- |
| Planning | `plan/` |
| Research | `research/` |
| Fitness | `fitness/` |
| Verification | `verify/` |
| PERSIST_RESULTS | `final/`, `logs/` |

---

# 6. Tool System

## Supervisor Tools

* `read_global_state`
* `classify_request`
* `partial_rerun_decision`
* `hitl_control`
* `persist_trigger`

## Planning Subgraph Tools

* `extract_profile`
* `validate_profile`
* `write_todos`

## Research Subgraph Tools (MCP for external data)

* `search_evidence`
* `retrieve_documents`
* `rank_sources`
* `verify_sources`

## Fitness Subgraph Tools

* `calculate_macros`
* `build_training_plan`
* `synthesize_plan`

## Verification Subgraph Tools

* `citation_check`
* `consistency_check`
* `safety_check`
* `ragas_faithfulness`

## HITL Subsystem Tools

* `request_clarification`
* `request_approval`

## PERSIST_RESULTS Tools

* `save_run`
* `save_metrics`
* `save_artifacts`

---

# 7. Subgraph Responsibilities

## SUPERVISOR (Orchestrator)

* Read/write orchestration state
* Classify request → `request_type`, `affected_domains`
* Route to subgraphs; never produce fitness content
* `partial_rerun_decision` for FIX_REASONING / REPLAN / RERESEARCH
* HITL control and persist trigger

## PLANNING SUBGRAPH (XHIGH)

* Extract and validate profile
* `write_todos` — mandatory before research
* Persist to `plan/`

## RESEARCH SUBGRAPH (STANDARD)

* Evidence retrieval via MCP only
* Rank and verify sources
* Persist to `research/`

## FITNESS SUBGRAPH (STANDARD)

* Macro targets, training plan, plan synthesis
* Apply verification feedback on FIX_REASONING
* Persist to `fitness/`

## VERIFICATION SUBGRAPH (XHIGH)

* Citation, consistency, safety checks
* RAGAS faithfulness (>= 0.90)
* Persist to `verify/`

## HITL SUBSYSTEM

* Clarification and approval interrupts
* Resume via checkpointer

## PERSIST_RESULTS

* Deterministic; runs after COMPLETE + approval

---

# 8. Model Strategy (Reasoning Sandwich)

| Subgraph | Tier |
| --- | --- |
| Planning | XHIGH |
| Verification | XHIGH |
| Supervisor | STANDARD |
| Research | STANDARD |
| Fitness | STANDARD |

---

# 9. Supervisor Routing Logic

| Decision | Condition | Target |
| --- | --- | --- |
| `FIX_REASONING` | Minor plan/macro issues, retry < 3 | Fitness → Verification |
| `REPLAN` | Structural/profile issues | Planning |
| `RERESEARCH` | Weak or insufficient evidence | Research → Fitness → Verification |
| `HITL` | Missing info, unsafe, retry exhausted, approval | HITL → Wait |
| `COMPLETE` | verify pass + faithfulness >= 0.90 + approved | PERSIST_RESULTS |

---

# 10. Checkpoint System

Checkpoint after: SUPERVISOR, each subgraph completion, HITL, PERSIST_RESULTS.

---

# 11. Completion Criteria

* Request classified; profile complete
* `write_todos` before MCP retrieval
* Research, fitness, verification subgraphs completed
* RAGAS faithfulness >= 0.90
* HITL approval received
* `PERSIST_RESULTS()` executed
* LangFuse trace with supervisor + subgraph spans

---

# 12. Core Product Behavior

```text id="product_01"
Fitness Training & Macro Engine

User Goal → Evidence → Training Plan + Macro Targets → Verified Output
```

---
