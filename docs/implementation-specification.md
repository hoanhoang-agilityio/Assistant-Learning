# THE CORE DEEP RESEARCHER (FITNESS AI)

## Phase 1 — Full Implementation Specification

---

# 1. System Overview

The Core Deep Researcher is a **Fitness-only AI Coaching & Research System**.

It transforms user fitness goals into:

* Evidence-based fitness plans
* Personalized nutrition strategies
* Training programs
* Behavioral coaching
* Verified actionable outputs

---

## NOT A GENERAL AI SYSTEM

The system does NOT support:

* Programming
* Finance
* Business analysis
* Legal advice
* General knowledge Q&A
* Medical diagnosis

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

# 3. Graph Architecture (DCG)

```text id="graph_01"
START
  ↓
DOMAIN_NODE
  ↓
FITNESS?

 ├── NO → OUT_OF_SCOPE_NODE → END

 └── YES
        ↓
INFO_CHECK_NODE
        ↓
COMPLETE?

 ├── NO → HITL_NODE → WAIT → INFO_CHECK_NODE

 └── YES
        ↓
PLAN_NODE
        ↓
RESEARCH_NODE
        ↓
DRAFT_NODE
        ↓
VERIFY_NODE
        ↓
ROUTER_NODE

 ├── FIX → FIX_NODE → VERIFY_NODE
 ├── REPLAN → REPLAN_NODE → RESEARCH_NODE
 ├── HITL → HITL_NODE
 └── PASS
        ↓
APPROVAL_NODE
        ↓
APPROVED?
 ├── NO → REPLAN_NODE
 └── YES
        ↓
PUBLISH_NODE
        ↓
EVALUATE_NODE
        ↓
PERSIST_NODE
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

    route_decision: str | None
    retry_count: int
    replan_count: int

    missing_fields: list[str]
    waiting_for_user: bool

    approval_status: str | None

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

├── intake/
│   ├── query.md
│   └── profile.json
│
├── plan/
│   ├── plan.md
│   └── todos.json
│
├── research/
│   ├── research_notes.md
│   ├── sources.json
│   └── findings.json
│
├── drafts/
│   ├── draft_v1.md
│   ├── draft_v2.md
│
├── verify/
│   ├── verification_v1.json
│   └── verification_v2.json
│
├── evaluation/
│   └── ragas.json
│
├── final/
│   └── final_plan.md
│
└── logs/
```

---

# 6. Tool System

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
  "calculate_calories",
  "build_meal_plan",
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

* calculate_calories
* calculate_macros
* build_meal_plan
* build_training_plan
* build_habit_plan
* supplement_research

---

## Draft Tools

* draft_plan

---

## Verification Tools (FR-2)

* citation_check
* consistency_check
* completeness_check
* llm_verifier

---

## Fix Tools

* fix_plan
* fix_citations
* fix_consistency

---

## HITL Tools

* request_clarification
* request_approval

---

## Evaluation Tools (OAC-2)

* ragas_faithfulness
* ragas_context_precision

---

## Persistence Tools

* save_run
* save_metrics
* save_artifacts

---

# 7. Node Responsibilities

## DOMAIN_NODE

* classify fitness / non-fitness

---

## INFO_CHECK_NODE

* validate profile completeness

---

## PLAN_NODE

* generate todos (write_todos)

---

## RESEARCH_NODE

* gather evidence

---

## DRAFT_NODE

* generate structured plan

---

## VERIFY_NODE

* full validation (rules + LLM)

---

## ROUTER_NODE

* decide:

  * PASS
  * FIX
  * REPLAN
  * HITL

---

## FIX_NODE

* repair issues

---

## REPLAN_NODE

* regenerate plan scope

---

## APPROVAL_NODE

* human approval gate

---

## PUBLISH_NODE

* final artifact generation

---

## EVALUATE_NODE

* RAGAS scoring

---

## PERSIST_NODE

* store run metadata

---

# 8. Model Strategy (Reasoning Sandwich)

| Node     | Tier     |
| -------- | -------- |
| PLAN     | XHIGH    |
| VERIFY   | XHIGH    |
| ROUTER   | XHIGH    |
| REPLAN   | XHIGH    |
| RESEARCH | STANDARD |
| DRAFT    | STANDARD |
| FIX      | STANDARD |

Graph NEVER sees model names.

---

# 9. LangFuse Observability

Every node creates spans:

* trace_id = run_id
* node-level spans required
* capture:

  * tokens
  * latency
  * tool calls
  * routing decisions

---

# 10. Checkpoint System

Checkpoint after EVERY node:

* PLAN
* RESEARCH
* DRAFT
* VERIFY
* ROUTER
* FIX
* REPLAN
* APPROVAL
* PERSIST

Recovery:

```text id="ckpt_01"
load checkpoint → resume node → continue execution
```

---

# 11. Router Logic

## PASS

* verification passed

---

## FIX

* minor issues

---

## REPLAN

* major structural issues

---

## HITL

* missing information
* conflicting data
* unclear objective

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

* Fitness domain validated
* Profile complete
* Plan generated
* Research completed
* Draft created
* Verification passed
* Human approved
* RAGAS evaluated
* Artifacts persisted
* LangFuse trace exists
* Checkpoint stored

---

# 14. Core Product Behavior

PT AI is NOT a chatbot.

It is a:

```text id="product_01"
Fitness Research & Coaching Engine
```

It converts:

```text id="product_02"
User Goal
→ Evidence
→ Structured Plan
→ Verified Output
→ Actionable Fitness Program
```

---
