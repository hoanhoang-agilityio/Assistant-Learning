# Implementation Detail — Custom Graph Architecture

Source of truth for this project. Transcribed from
[`generative-ai-training-plan.pdf`](generative-ai-training-plan.pdf) (Agility IO, Aug 18 2026).
Task breakdown and progress live in [`estimation.md`](estimation.md).

Engineering conventions for `src/` come from the `langgraph-agent-arch` skill
(`.claude/skills/langgraph-agent-arch/`). This document says *what* to build; the skill says *how*.

---

## 1. Node design

**Superseded by the supervisor migration** (28/08) — see
[`supervisor-migration.md`](supervisor-migration.md) §1 for the current node table and the
reasoning behind each change. Node names and branch labels are still each defined once, in
`src/enums/` — `Node` in `graph.py`, the routers' answers in `routes.py` — and the route tables
that map one to the other live in `src/constants/routes.py`; `src/graph.py`, the route functions
and the tests reference those rather than repeating strings.

The fixed pipeline this section originally described (`parse_turn` classifying intent once up
front, then branching for the rest of the turn) is gone. In its place, `supervisor` decides one
agent at a time — `user_agent`, `coach_agent` or `qa_agent` — in a loop, until it decides
`FINISH`; every branch returns to it through `summarize` rather than converging on a single
`finalize_turn`. `src/core/langgraph/` ran this section's original pipeline unchanged until the
Milestone 11 cutover (28/08) deleted it; the deviations table below is kept for the reasoning
behind each name, even though the "old pipeline only" nodes it references no longer exist.

### Deviations from the PDF spec, and why

| Spec | Built | Reason |
|---|---|---|
| `llm_guard` | `guard_input` | The library is `llm-guard`; the node makes no LLM call, and the old name said it did |
| `classify_intent` + `determine_context` + `save_user_data` | `parse_turn` + `merge_profile` + `persist_profile` (old pipeline only — see above) | Classification and extraction are one structured read of one message, so they are one call. Merging is deterministic and belongs in its own testable node; the write is a third, separate concern |
| `load_context` | `load_user_context` | It reads user-scoped long-term memory, not thread state — thread state is the checkpointer |
| `request_missing_info` / `user_info_exhausted` | `request_missing_profile_fields` / `profile_collection_exhausted` (old pipeline only) | Say which data |
| `ragas_verification` | `verify_faithfulness` | Do not name a node after the library that happens to implement it |
| `write_todo` | *(removed)* | Never wired into the graph, and `GraphState` had no `todo` key, so every write was silently dropped. The coach agent's own prompt already sequences the work |
| `hitl_review` approve → `END` | (old pipeline) approve → `finalize_turn` → `END`; (current) `hitl_agent` coach·approve → `commit_plan` → `summarize` | The spec has no node that persists an approved plan, so `recall_plan` had no writer and `load_user_context` always returned `plan: None` |
| — | `user_agent`, `hitl_agent`, `commit_plan`, `commit_profile_update`, `summarize` | Not in the PDF spec at all — added by the supervisor migration; see `supervisor-migration.md` §1 for what each does |

## 2. Edge / routing design

**Superseded by the supervisor migration** — see [`supervisor-migration.md`](supervisor-migration.md)
§2 for the current routing table. Only two edges in the current graph reach `END`: `guard_input`'s
block, and `supervisor`'s own `FINISH` decision; every other node returns to `supervisor` through
`summarize`, which replaces the fixed pipeline's single `finalize_turn` convergence point.

The old pipeline's routing, until it was deleted at the Milestone 11 cutover (28/08), was
unchanged from what this section originally described: `request_missing_profile_fields →
wait_for_user → parse_turn` was its interrupt loop, resuming through `parse_turn` because that is
where the reply was read; re-entering `parse_turn` let the user change the subject
mid-collection, bounded by *sticky intent* — while `missing_fields` was non-empty, a message that
stated at least one profile field kept the intent that opened the loop. That loop was bounded by
`user_info_retry_count`, and both its branches shared `load_user_context → merge_profile →
persist_profile`. None of that carried forward: the current pipeline has no upfront intent
classification to stay sticky to, and `user_agent` asks for missing fields conversationally
instead of through a template node — see `supervisor-migration.md` §1's "Removed" table and §4
for what replaced it and what was deliberately dropped rather than ported.

The three diagrams that used to render here (generated from the old pipeline's
`build_graph()` by `scripts/export_graph_diagrams.py`) were removed at the Milestone 11
cutover along with the code they depicted. [`supervisor-workflow.html`](supervisor-workflow.html)
is the authoritative diagram for the current topology; regenerating an equivalent "one view
per intent" set for the new graph is not planned, since a supervisor that can visit more
than one agent per turn does not split into per-intent views the same way.

## 3. State design

See [`state-design.md`](state-design.md) for the literal schema from the spec.

## 4. Agent design

### Coach agent

Generate or modify a personalized training plan based on the user's profile, goal, constraints and
todo list.

Input: `user_query`, `profile`, `plan` (if an existing plan is available), `messages`.
Output: training plan — goal, calories, macro, training days, exercises.

| Tool | Purpose |
|---|---|
| `load_template` | Retrieve a suitable training plan template |
| `load_exercise` | Retrieve exercises matching training requirements and constraints |
| `recall_memory` | Retrieve the user's stored preferences and accumulated knowledge |
| `calc_macro` | Calculate calorie and macro targets |

### QA agent

Answer nutrition and injury-related knowledge questions using the retrieved local knowledge base.

Input: `user_query`, `profile` (when relevant), `messages`. Output: `answer`.

| Tool | Purpose |
|---|---|
| `search_knowledge` | Retrieve relevant passages from the local knowledge base |
| `calc_macro` | Calculate calorie and macro targets to answer a question relative to the user |

## 5. Verification design

### Deterministic verification

Validate the training plan using fixed rules, without an LLM. Checks:

- Schema completeness
- Macro consistency
- Training volume
- Training schedule
- Exercise availability
- User constraints
- Safety constraints

Threshold: fail and `coach_retry_count < 3` → return the validation errors to `coach_agent` for
revision. Fail after 3 attempts → route to `notify_fail`.

### RAGAS verification

Validate QA answer faithfulness against retrieved context.

- `ragas_score >= 0.9` → pass
- `ragas_score < 0.9` → retry QA agent; still below 0.9 after 3 attempts → `qa_fallback`

## 6. HITL design

```
Generated Plan
     ↓
Deterministic Verification
     ↓
  hitl_review
     ↓
┌────┴────┐
approve   reject
   ↓         ↓
finalize   feedback?
_turn       /     \
   ↓      yes      no
  end      ↓        ↓
      coach_agent  stop
```

- **Approve** — `finalize_turn` writes the plan to the `plan` namespace and confirms it to the user.
- **Reject with feedback** — pass `hitl_feedback` to `coach_agent`, regenerate/revise the plan,
  increment `hitl_retry_count`.
- **Reject without feedback** — route to `hitl_rejected_no_feedback` and stop.
- **Retry limit** — more than 3 rejects with feedback → `hitl_exhausted`, stop.
- `hitl_review` uses `interrupt()`; the checkpoint preserves `GraphState` so the graph resumes after
  the user responds.

## 7. Memory & persistence design

### Short-term memory

Checkpointer: `AsyncPostgresSaver`.

- Store graph checkpoints in PostgreSQL.
- Preserve `GraphState` during graph execution.
- Support graph resume after `interrupt()`.

Short-term memory is for the **current workflow execution**, not persistent user knowledge.

### Long-term memory

**pgvector** — `knowledge_chunks` stores embedded knowledge from nutrition and injury documents.

**PostgresStore** — structured user-specific information:

- *User preferences*: preferred workout schedule, favorite exercises, dietary preferences,
  preferred response style.
- *Accumulated knowledge*: behavioral patterns learned over time, e.g. tendency to skip workouts
  longer than 60 minutes, or better adherence to 4-day plans.
- *Facts*: name, age, weight, sex, activity level, goal, equipment, injury.

All three are addressed as `("users", user_id, scope)` and reached through `src/services/memory.py`
— the one gateway to the store. Facts are what `load_user_context` reads and `persist_profile` writes;
preferences and accumulated knowledge reach the coach agent through the `recall_memory` tool.

> **Deviation (03/09).** Not built as specified. The supervisor migration removed the node that
> wrote preferences, leaving `recall_memory` to answer "nothing recorded" for every user, so the
> tool, `src/services/preferences.py` and `src/services/turn.py` were deleted. `MemoryScope` was
> then narrowed to *facts*, the one scope with a writer: an addressable scope nothing fills reads
> as working memory right up until every lookup comes back empty. The store today holds the
> profile under `("users", user_id, "facts")` and the plan under `("users", user_id, "plan")`.

## 8. RAG design

![RAG flow](diagrams/rag-flow.png)

### Retrieval

- Embedding model: `text-embedding-3-small`
- Similarity: cosine similarity
- `top_k = 4`
- Filter using a tuned similarity threshold
- Remove duplicate or highly overlapping chunks

Retrieval output:

```python
{"text": str, "source": str, "score": float}
```

Return `[]` when no passage meets the configured threshold.

### No relevant context

If no relevant passage is retrieved, the QA agent must **not** answer using unsupported knowledge.
Return a fallback response indicating that sufficient trusted information is unavailable.

### Evaluation

Offline: context precision, faithfulness — used to tune the retrieval threshold.
Online: RAGAS faithfulness >= 0.9 is required before returning the QA answer.

## 9. Error handling

| Error | Handling |
|---|---|
| LLM failure | Retry according to agent retry policy |
| Tool failure | Retry agent/tool call |
| Invalid agent output | Retry agent with validation error |
| Guard failure | Block request |
| Deterministic verification failure | Retry coach agent up to 3 times |
| RAGAS failure | Retry QA agent up to 3 times |
| HITL rejection with feedback | Revise plan |
| HITL rejection without feedback | Stop workflow |
| HITL retry exhausted | Stop workflow and notify user |
| User info retry exhausted | Stop workflow and tell the user no plan was built |
| No relevant RAG context | Return untrusted/insufficient-context response |

All retry limits are controlled by the corresponding retry counter in `GraphState`.

## 10. Observability

Use Langfuse to trace each graph execution and major workflow step. Track: `run_id`, `user_id`,
`intent`, node execution, agent execution, tool calls, retrieved chunks and similarity scores,
retry counts, verification results, RAGAS score, latency, final result.

## 11. Pydantic data models

See [`data-models.md`](data-models.md) for the full enum and schema specification.
