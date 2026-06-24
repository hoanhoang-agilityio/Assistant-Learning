# Phase 1 — Core Deep Researcher

## Objective

Build a production-grade Deep Research Agent with:

* Structured planning (task decomposition)
* Evidence-based research
* Iterative Build-Verify-Fix reliability loop
* Durable execution with crash recovery
* Human-in-the-loop safety gates
* Full observability & evaluation framework

---

# 1. System Architecture Overview

## High-Level Flow

```text id="arch_01"
User Query
    ↓
PLAN (XHIGH)
    ↓
write_todos()
    ↓
RESEARCH (STANDARD)
    ↓
DRAFT (STANDARD)
    ↓
VERIFY (XHIGH)
    ↓
ROUTER (XHIGH)
    ├── FIX → VERIFY
    ├── REPLAN → PLAN
    ├── HITL → HUMAN INPUT
    └── PASS
            ↓
     APPROVAL GATE (HITL)
            ↓
       PUBLISH
            ↓
        PERSIST
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

---

# 2. Graph Architecture (LangGraph DCG)

## Nodes

### PLAN_NODE (XHIGH)

* Goal decomposition
* Task breakdown via `write_todos`
* Planning strategy creation

Outputs:

```text
plan.md
todos.json
```

---

### RESEARCH_NODE (STANDARD)

* Web search
* RAG retrieval
* Evidence collection

Outputs:

```text
research_notes.md
sources.json
findings.json
```

---

### DRAFT_NODE (STANDARD)

* Synthesis
* Artifact generation

Outputs:

```text
draft_vN.md
```

---

### VERIFY_NODE (XHIGH)

Hybrid verification:

* Programmatic verification (tests, schemas, citations)
* LLM verification (reasoning-based evaluation)

Outputs:

```text
verification.json
test_results.json
```

---

### ROUTER_NODE (XHIGH)

Decides:

```text
PASS | FIX | REPLAN | HITL | FAIL
```

---

### FIX_NODE (STANDARD)

* Fix formatting issues
* Repair missing citations
* Patch minor logical issues

---

### REPLAN_NODE (XHIGH)

* Rewrite plan
* Expand research scope
* Fix structural issues

---

### HITL_NODE

* Human clarification
* Human decision input
* Interrupt/resume support

---

### APPROVAL_NODE (HITL)

* Final approval gate before persistence
* Required for all permanent writes

---

### PUBLISH_NODE

* Generate final artifacts (markdown, JSON, PDF, DOCX)

---

### PERSIST_NODE

* Save metadata, traces, costs, and final outputs

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
    │   └── todos.json
    │
    ├── research/
    │   ├── research_notes.md
    │   ├── sources.json
    │   ├── findings.json
    │
    ├── drafts/
    │   ├── draft_v1.md
    │   ├── draft_v2.md
    │
    ├── verify/
    │   ├── verification_v1.json
    │   └── test_results.json
    │
    ├── final/
    │   └── final_output.md
    │
    └── logs/
        └── trace.jsonl
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

Agent MUST generate structured todos BEFORE any retrieval.

---

### Flow

```text id="fr1_flow"
User Query
    ↓
PLAN_NODE
    ↓
write_todos()
    ↓
todos.json
    ↓
RESEARCH
```

---

### Purpose

* Execution contract
* Task decomposition
* Future parallelization foundation

---

## FR-2: Build-Verify-Fix (BVF Loop)

### Requirement

Agent MUST NOT terminate until verification passes.

---

### Loop

```text id="bvf"
BUILD
↓
VERIFY
↓
FIX
↓
VERIFY
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

* Planning
* Verification
* Routing
* Replanning

---

### STANDARD Models

Used for:

* Research
* Drafting
* Fixing

---

## Node Mapping

| Node     | Tier     |
| -------- | -------- |
| PLAN     | XHIGH    |
| VERIFY   | XHIGH    |
| ROUTER   | XHIGH    |
| REPLAN   | XHIGH    |
| RESEARCH | STANDARD |
| DRAFT    | STANDARD |
| FIX      | STANDARD |

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

* Nutrition
* Exercise
* Coaching
* Research QA

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
VERIFY
↓
PASS
↓
APPROVAL_NODE (HITL)
↓
PUBLISH
↓
PERSIST
```

---

## Approval Modes

### Approve

→ write final artifacts

### Reject

→ FIX or REPLAN

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

1. No direct model calls inside nodes
2. All reasoning artifacts go to VFS
3. State must remain minimal
4. All execution must be checkpointable
5. No final output without approval
6. No termination without verification pass

---
