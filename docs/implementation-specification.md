# THE CORE DEEP RESEARCHER (FITNESS AI)

## Phase 1 — Full Implementation Specification

---

# 1. System Overview

The Core Deep Researcher is a **Fitness Training & Macro System**.

It transforms user fitness goals into:

* Evidence-based training plans
* Macro targets (calories, protein, carbs, fat)
* Verified actionable outputs

The implementation uses a lean multi-agent architecture with exactly 5 LLM agents. The supervisor is a rule-based router (STANDARD tier). Orchestration-only concerns (HITL interrupt, persistence) are handled deterministically without additional agents.

---

## NOT A GENERAL AI SYSTEM

The system does NOT support:

* Programming
* Finance
* Business analysis
* Legal advice
* General knowledge Q&A
* Medical diagnosis
* Meal planning
* Nutrition coaching
* Diet plans
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

---

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

# 3. Graph Architecture (5-Agent DCG)

```text id="graph_01"
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

---

# 4. State Contract

```python id="state_01"
class AgentState(TypedDict):
    run_id: str
    thread_id: str
    query: str

    route_decision: str | None       # FIX_LOOP | REPLAN | HITL | COMPLETE
    retry_count: int
    replan_count: int

    missing_fields: list[str]
    waiting_for_user: bool

    approval_status: str | None

    verification_passed: bool
    faithfulness_score: float | None
    current_node: str
    workspace_path: str
    final_artifact_path: str | None
```

---

## Principle

DON'T store:

* drafts
* research notes
* verification outputs

✔ All stored in VFS only

---

# 5. Workspace (VFS)

```text id="vfs_01"
workspace/run_<id>/

├── plan/
│   ├── plan.md
│   ├── todos.json
│   └── profile.json
│
├── research/
│   ├── research_notes.md
│   ├── sources.json
│   └── findings.json
│
├── fitness/
│   ├── calculations.json
│   ├── safety_flags.json
│   └── final_plan.md
│
├── verify/
│   ├── verification_v1.json
│   └── ragas.json
│
├── final/
│   └── final_plan.md
│
└── logs/
    ├── supervisor_decisions.jsonl
    └── persist_result.json
```

---

# 6. Agent Tool System

---

## Agent Ownership (5 agents only)

| Agent | Owns | Notes |
| --- | --- | --- |
| Supervisor Agent | rule-based routing, retries, HITL triggers | STANDARD tier — reads verification JSON, no LLM reasoning |
| Planning Agent | domain check, profile extraction, `write_todos`, plan | XHIGH — absorbs former Intake Agent |
| Research Agent | external evidence retrieval | Must use MCP clients only |
| Fitness Reasoning Agent | calculations, safety, plan synthesis | Absorbs former Draft + Fix Agent |
| Verification Agent | validation + RAGAS faithfulness | XHIGH — absorbs former Evaluation Agent |

Non-agent: `HITL interrupt` (LangGraph), `PERSIST_RESULTS()` (deterministic)

---

## Planning

### write_todos (FR-1)

```json id="tool_01"
{
  "goal": "lose weight"
}
```

---

## Output

```json id="tool_02"
[
  "collect_profile",
  "calculate_macros",
  "build_training_plan"
]
```

---

## Profile Tools

* extract_profile
* validate_profile

---

## Research Tools

* search_evidence
* retrieve_documents
* source_ranker
* source_verifier

---

## Fitness Domain Tools

* calculate_macros
* build_training_plan

---

## Draft Tools (Fitness Reasoning Agent)

* synthesize_plan
* fix_plan_from_verification_feedback

---

## Verification Tools (FR-2)

* citation_check
* consistency_check
* completeness_check
* safety_check
* llm_verifier
* ragas_faithfulness

---

## HITL Tools (Supervisor — LangGraph interrupt)

* request_clarification
* request_approval

---

## Persistence (PERSIST_RESULTS — deterministic)

* save_run
* save_metrics
* save_artifacts

---

# 7. Node Responsibilities

## SUPERVISOR_NODE (STANDARD — rule-based)

* Route based on verification JSON and state flags
* Decide `FIX_LOOP`, `REPLAN`, `HITL`, or `COMPLETE`
* Maintain retry and replan counters
* Trigger HITL interrupt for approval before `PERSIST_RESULTS()`
* Write routing decisions to `logs/supervisor_decisions.jsonl`

---

## PLANNING_NODE (XHIGH)

* Classify fitness / non-fitness domain
* Extract and validate profile fields
* Generate todos (`write_todos`) — must run before retrieval
* Trigger HITL if profile incomplete or goal ambiguous

---

## RESEARCH_NODE (STANDARD)

* Gather evidence through MCP clients only

---

## FITNESS_REASONING_NODE (STANDARD)

* Calculate macro targets (calories, protein, carbs, fat)
* Training constraints, recovery guidance
* Run safety checks
* Synthesize final plan → `fitness/final_plan.md`
* Re-run with verification feedback on FIX_LOOP

---

## VERIFICATION_NODE (XHIGH)

* Programmatic validation (schemas, citations, safety, consistency)
* LLM verification
* RAGAS faithfulness scoring (target >= 0.90)

---

## HITL interrupt (non-agent)

* LangGraph interrupt — clarification, approval, retry exhaustion
* Resume via checkpointer

---

## PERSIST_RESULTS() (non-agent)

* Copy approved plan to `final/final_plan.md`
* Save run metadata and trace references

---

# 8. Model Strategy (Reasoning Sandwich)

| Agent | Tier |
| --- | --- |
| Planning Agent | XHIGH |
| Verification Agent | XHIGH |
| Supervisor Agent | STANDARD |
| Research Agent | STANDARD |
| Fitness Reasoning Agent | STANDARD |

Only Planning and Verification use XHIGH. Supervisor routing is rule-based.

---

# 9. LangFuse Observability

Every node creates spans:

* trace_id = run_id
* node-level spans required
* agent-level spans required
* capture:

  * tokens
  * latency
  * tool calls
  * routing decisions
  * VFS reads/writes
  * MCP server names

---

# 10. Checkpoint System

Checkpoint after EVERY agent node:

* SUPERVISOR
* PLANNING
* RESEARCH
* FITNESS_REASONING
* VERIFICATION
* HITL (interrupt/resume)
* PERSIST_RESULTS

Recovery:

```text id="ckpt_01"
load checkpoint → resume node → continue execution
```

---

# 11. Supervisor Routing Logic

## COMPLETE

* verification passed
* faithfulness score >= 0.90
* HITL approval received
* triggers `PERSIST_RESULTS()`

---

## FIX_LOOP

* minor issues in verification JSON
* retry_count < 3
* routes back to FITNESS_REASONING_NODE with feedback

---

## REPLAN

* major structural issues
* insufficient evidence
* unsafe recommendation pattern
* routes back to PLANNING_NODE

---

## HITL

* missing profile fields (from PlanningAgent)
* conflicting or unsafe user constraints
* retry_count >= 3
* final approval before persistence

---

# 12. HITL Flow

## Clarification

```text id="hitl_01"
missing profile fields → pause → wait user input
```

---

## Approval

```text id="hitl_02"
final plan → user approval → persist
```

---

# 13. Completion Criteria

System is COMPLETE only when:

* Fitness domain validated (PlanningAgent)
* Profile complete
* `write_todos` executed before retrieval
* Research completed via MCP
* Fitness reasoning + plan synthesis completed
* Verification passed with RAGAS faithfulness >= 0.90
* Human approved via HITL
* `PERSIST_RESULTS()` executed
* LangFuse trace exists with 5 agent spans
* Checkpoint stored

---

# 14. Core Product Behavior

PT AI is NOT a chatbot.

It is a:

```text id="product_01"
Fitness Training & Macro Engine
```

It converts:

```text id="product_02"
User Goal
→ Evidence
→ Training Plan + Macro Targets
→ Verified Output
```

---
