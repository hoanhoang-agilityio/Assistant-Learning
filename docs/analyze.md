# Phase 1 — Core Deep Researcher

## Objective

Build a production-grade PT AI Deep Research system with:

* Structured planning (task decomposition)
* Evidence-based research
* Iterative Build-Verify-Fix reliability loop
* Durable execution with crash recovery
* Human-in-the-loop safety gates
* Full observability & evaluation framework
* Supervisor-led multi-agent delegation

---

# 1. System Architecture Overview

## High-Level Flow

Only agents that create intelligence are kept. Orchestration-only nodes (intake, draft, fix, publish, persist) are merged or replaced with deterministic logic.

```text id="arch_01"
User Query
    ↓
SUPERVISOR (STANDARD)
    ↓
PLANNING AGENT (XHIGH)
    ↓
write_todos()
    ↓
RESEARCH AGENT (STANDARD)
    ↓
FITNESS REASONING AGENT (STANDARD)
    ↓
VERIFICATION AGENT (XHIGH)
    ↓
SUPERVISOR (STANDARD)
    ├── FIX_LOOP → FITNESS REASONING AGENT
    ├── REPLAN → PLANNING AGENT
    ├── HITL
    └── COMPLETE
            ↓
     PERSIST_RESULTS()
            ↓
        FINAL ARTIFACT
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

See `docs/multi-agent-implementation-plan.md` for the detailed supervisor-agent implementation plan.

---

# 2. Graph Architecture (LangGraph DCG)

## Intelligence Agents (5 only)

The graph is a DCG with 5 LLM agents. The `SUPERVISOR_NODE` is a rule-based router — no LLM reasoning required. Non-agent components (`HITL interrupt`, `PERSIST_RESULTS()`) are deterministic.

| Agent | Tier | Responsibility |
| --- | --- | --- |
| Supervisor Agent | STANDARD | Rule-based routing, retries, HITL triggers, acceptance gates |
| Planning Agent | XHIGH | Domain check, profile extraction, objective decomposition, `write_todos` |
| Research Agent | STANDARD | Evidence retrieval through MCP clients |
| Fitness Reasoning Agent | STANDARD | Calculations, safety checks, plan synthesis |
| Verification Agent | XHIGH | Programmatic + LLM verification, RAGAS faithfulness |

---

## Nodes

### SUPERVISOR_NODE (STANDARD — rule-based, no LLM)

* Route to next agent based on state flags and verification JSON
* Retry and replan counting
* HITL interrupt triggers
* Approval gate enforcement before `PERSIST_RESULTS()`

Outputs:

```text
logs/supervisor_decisions.jsonl
```

---

### PLANNING_NODE / Planning Agent (XHIGH)

* Fitness domain classification
* Profile extraction and completeness check
* Goal decomposition via `write_todos`
* HITL trigger if profile incomplete

Outputs:

```text
plan/plan.md
plan/todos.json
plan/profile.json
```

---

### RESEARCH_NODE / Research Agent (STANDARD)

* Web search through MCP
* RAG retrieval through MCP
* Evidence collection

Outputs:

```text
research/research_notes.md
research/sources.json
research/findings.json
```

---

### FITNESS_REASONING_NODE / Fitness Reasoning Agent (STANDARD)

* Macro target calculation
* Training and recovery constraints
* Safety checks
* Plan synthesis (absorbs former Draft Agent)

Outputs:

```text
fitness/calculations.json
fitness/safety_flags.json
fitness/final_plan.md
```

---

### VERIFY_NODE / Verification Agent (XHIGH)

Hybrid verification + RAGAS evaluation:

* Programmatic verification (schemas, citations, safety)
* LLM verification (reasoning-based evaluation)
* RAGAS faithfulness scoring

Outputs:

```text
verify/verification_vN.json
verify/ragas.json
```

---

### HITL interrupt (non-agent)

* LangGraph interrupt — not a separate LLM agent
* Human clarification, approval, unsafe goal review
* Resume via checkpointer

---

### PERSIST_RESULTS() (non-agent)

* Deterministic function — not an LLM agent
* Copies approved plan to `final/final_plan.md`
* Saves run metadata and trace references

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

The Planning Agent MUST generate structured todos BEFORE any retrieval.

---

### Flow

```text id="fr1_flow"
User Query
    ↓
SUPERVISOR_NODE
    ↓
PLANNING_NODE
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

The Supervisor Agent MUST NOT allow successful termination until verification passes.

---

### Loop

```text id="bvf"
FITNESS_REASONING (build)
    ↓
VERIFICATION
    ↓
SUPERVISOR
    ├── FIX_LOOP → FITNESS_REASONING
    ├── REPLAN → PLANNING
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

| Agent | Tier |
| --- | --- |
| Planning | XHIGH |
| Verification | XHIGH |
| Supervisor | STANDARD |
| Research | STANDARD |
| Fitness Reasoning | STANDARD |

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

→ FIX_LOOP (Fitness Reasoning) or REPLAN (Planning)

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

1. Only 5 LLM agents — no orchestration-only agents
2. Supervisor routing is rule-based, not LLM-driven
3. All reasoning artifacts go to VFS
4. State must remain minimal
5. All execution must be checkpointable
6. No final output without HITL approval
7. No termination without verification pass
8. RAGAS runs inside VerificationAgent, not as separate agent

---
