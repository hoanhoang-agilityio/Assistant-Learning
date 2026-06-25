# Phase 1 — Core Deep Researcher

## Objective

Build a production-grade PT AI Deep Research system with:

* Structured planning (task decomposition)
* Evidence-based research
* Iterative Build-Verify-Fix reliability loop
* Durable execution with crash recovery
* Human-in-the-loop safety gates
* Full observability & evaluation framework
* Supervisor-orchestrated subgraph architecture

---

# 1. System Architecture Overview

## High-Level Flow

Supervisor orchestrates 4 intelligence subgraphs. Global orchestration state is separate from subgraph-scoped state. Artifacts persist to VFS.

```text id="arch_01"
START
    ↓
SUPERVISOR (ORCHESTRATOR)
    ↓
PLANNING → RESEARCH → FITNESS → VERIFICATION
    ↓
SUPERVISOR
    ├── FIX_REASONING → FITNESS
    ├── REPLAN        → PLANNING
    ├── RERESEARCH    → RESEARCH
    ├── HITL          → WAIT → SUPERVISOR
    └── COMPLETE      → PERSIST_RESULTS → END
```

---

## Core Infrastructure

| Layer               | Technology                             |
| ------------------- | -------------------------------------- |
| Orchestration       | LangGraph (DCG)                        |
| API                 | FastAPI                                |
| Storage (Artifacts) | Virtual File System (VFS)              |
| State Persistence   | LangGraph Checkpointer (PostgresSaver) |
| Observability       | LangFuse                               |
| Evaluation          | RAGAS                                  |
| Model Routing       | Reasoning Sandwich                     |
| Database            | PostgreSQL                             |
| UI                  | Streamlit                              |

See `docs/multi-agent-implementation-plan.md` for the full subgraph orchestration diagram.

---

# 2. Graph Architecture (LangGraph DCG)

## Subgraphs (4 intelligence units)

| Subgraph | Tier | Responsibility |
| --- | --- | --- |
| Supervisor | STANDARD | Orchestrator — route, partial rerun, HITL, persist trigger |
| Planning | XHIGH | Profile extraction, validation, `write_todos` |
| Research | STANDARD | Evidence retrieval via MCP |
| Fitness | STANDARD | Macro targets, training plan, plan synthesis |
| Verification | XHIGH | Citation, consistency, safety, RAGAS |

Non-subgraph: **HITL subsystem**, **PERSIST_RESULTS**

---

## Orchestration State vs Subgraph State

**Global (OrchestrationState)** — checkpointer:

```text
run_id, thread_id, current_node
query, user_profile, constraints
request_type, affected_domains
route_decision, retry_count, replan_count
verification_passed, faithfulness_score
waiting_for_user, approval_status, user_response
workspace_path, final_artifact_path
```

**Scoped per subgraph:**

| Subgraph | State fields |
| --- | --- |
| Planning | profile, missing_fields, todos, planning_output |
| Research | research_questions, evidence, sources, evidence_summary |
| Fitness | macro_targets, training_constraints, training_plan, draft_plan, safety_flags |
| Verification | verification_report, feedback, faithfulness_score, pass_fail |

---

## Nodes

### SUPERVISOR (ORCHESTRATOR)

Tools: `read_global_state`, `classify_request`, `route_subgraph`, `partial_rerun_decision`, `hitl_control`, `persist_trigger`

* Route subgraphs based on orchestration state
* Partial rerun: FIX_REASONING, REPLAN, RERESEARCH
* HITL control and persist trigger

---

### PLANNING SUBGRAPH (XHIGH)

Tools: `extract_profile`, `validate_profile`, `write_todos`

Outputs → VFS `plan/`

---

### RESEARCH SUBGRAPH (STANDARD)

Tools: `search_evidence`, `retrieve_documents`, `rank_sources`, `verify_sources` (MCP for external)

Outputs → VFS `research/`

---

### FITNESS SUBGRAPH (STANDARD)

Tools: `calculate_macros`, `build_training_plan`, `synthesize_plan`

Outputs → VFS `fitness/`

---

### VERIFICATION SUBGRAPH (XHIGH)

Tools: `citation_check`, `consistency_check`, `safety_check`, `ragas_faithfulness`

Outputs → VFS `verify/`

---

### HITL SUBSYSTEM

Tools: `request_clarification`, `request_approval`

---

### PERSIST_RESULTS

Tools: `save_run`, `save_metrics`, `save_artifacts`

---

# 3. Virtual File System (VFS)

## Principle

* VFS is the **source of truth for reasoning artifacts**
* LangGraph state stores only execution metadata

---

## Workspace Structure

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

## VFS Interface

```python
class VFS:
    def read(path: str) -> str: ...
    def write(path: str, content: str): ...
    def exists(path: str) -> bool: ...
    def append(path: str, content: str): ...
```

---

# 4. Functional Requirements

---

## FR-1: Strategic Planning (write_todos)

### Requirement

The Planning Subgraph MUST generate structured todos BEFORE any retrieval.

---

### Flow

```text id="fr1_flow"
User Query
    ↓
SUPERVISOR (route_subgraph)
    ↓
PLANNING SUBGRAPH
    ↓
write_todos()
    ↓
todos.json → VFS plan/
    ↓
RESEARCH SUBGRAPH
```

---

### Purpose

* Execution contract
* Task decomposition
* Future parallelization foundation

---

## FR-2: Build-Verify-Fix (BVF Loop)

### Requirement

The Supervisor MUST NOT trigger COMPLETE until verification passes.

---

### Loop

```text id="bvf"
FITNESS SUBGRAPH (build)
    ↓
VERIFICATION SUBGRAPH
    ↓
SUPERVISOR
    ├── FIX_REASONING → FITNESS
    ├── REPLAN        → PLANNING
    ├── RERESEARCH    → RESEARCH
    └── HITL (retry_count >= 3)
```

---

### Verification Types

* Programmatic tests (lint, schema, citation checks)
* LLM evaluation

---

### Constraint

```text
MAX_FIX_ATTEMPTS = 3
```

If exceeded → HITL

---

## FR-3: Durable Persistence (Checkpointer)

### Requirement

System MUST support:

* Resume after crash
* Resume after interrupt
* Long-running execution recovery

---

## Design

### Checkpointer stores execution state

```json
{
  "run_id": "...",
  "current_node": "VERIFY",
  "retry_count": 2
}
```

---

### VFS stores reasoning state

* plans
* drafts
* research
* verification outputs

---

## Recovery Flow

```text
Crash
↓
Load checkpoint
↓
Resume current node
↓
Continue execution
```

---

## Implementation

* LangGraph PostgresSaver (required)
* thread_id = run_id

---

# 5. Compute Strategy (Reasoning Sandwich)

## Model Routing Strategy

### XHIGH Models

Used for:

* Planning (start of Reasoning Sandwich)
* Verification + RAGAS (end of Reasoning Sandwich)

---

### STANDARD Models

Used for:

* Supervisor routing (rule-based, minimal LLM if any)
* Research
* Fitness reasoning and plan synthesis

---

## Node Mapping

| Subgraph | Tier |
| --- | --- |
| Planning | XHIGH |
| Verification | XHIGH |
| Supervisor | STANDARD |
| Research | STANDARD |
| Fitness | STANDARD |

---

## Key Rule

> Graph MUST NOT know model names — only tiers.

---

# 6. Observability & Acceptance Criteria

---

## OAC-1: Trace Fidelity (LangFuse)

### Requirement

Every execution MUST generate full trace hierarchy:

* Thread
* Trace
* Node execution spans

---

### Observability Includes:

* Node execution timing
* Tool calls
* LLM calls
* Routing decisions
* Token usage

---

### Required Tooling

* LangFuse integration (mandatory)

---

## OAC-2: Performance Target (RAGAS)

### Requirement

> Answer Faithfulness ≥ 0.90

---

## Evaluation Method

Input:

* final answer
* retrieved context

Output:

* Faithfulness score

---

## Execution Mode

* CI / nightly evaluation
* benchmark datasets

---

## Dataset Categories

* Macro Calculation
* Training

---

## Failure Condition

* No evaluation pipeline = invalid system
* Faithfulness < 0.90 = regression

---

## OAC-3: Safety Gate (Human Approval)

### Requirement

System MUST require human approval before:

* Any permanent file writes
* Final output persistence

---

## Flow

```text
VERIFICATION PASS
↓
SUPERVISOR → HITL (approval interrupt)
↓
User APPROVED
↓
PERSIST_RESULTS()
```

---

## Approval Modes

### Approve

→ write final artifacts

### Reject

→ FIX_REASONING (Fitness) or REPLAN (Planning) or RERESEARCH (Research)

---

## Safety Guarantee

Agent CANNOT bypass approval gate.

---

# 7. Final System Properties

---

## Reliability

* BVF loop enforced
* Programmatic verification mandatory
* Retry bounded (max 3)

---

## Durability

* Checkpoint-based recovery
* Stateless VFS reasoning layer
* Resume from crash or interrupt

---

## Observability

* Full LangFuse trace hierarchy
* Tool + LLM + node visibility

---

## Quality

* RAGAS Faithfulness ≥ 0.90
* Regression testing required

---

## Safety

* Human approval required before persistence
* HITL interrupts enforced

---

## Architecture Integrity Rules

1. Supervisor orchestrates; subgraphs produce intelligence
2. Orchestration state vs subgraph-scoped state are separated
3. Partial rerun: FIX_REASONING, REPLAN, RERESEARCH
4. All reasoning artifacts go to VFS
5. Global state stores orchestration metadata only
6. No final output without HITL approval
7. No termination without verification pass
8. RAGAS runs inside Verification subgraph

---
