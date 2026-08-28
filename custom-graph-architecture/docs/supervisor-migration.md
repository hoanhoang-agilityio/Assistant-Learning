# Supervisor migration

Replaces the intent-routed fixed pipeline (`parse_turn` → branch on `Intent`) with a supervisor
router that decides one agent at a time, in a loop, until it decides `FINISH`. The two existing
sub-pipelines — coaching and QA — are **not rewritten**; only how they're entered and exited
changes. Design discussion and the diagram this doc implements:
[`docs/supervisor-workflow.html`](supervisor-workflow.html). The target state
shape is already committed in [`src/schemas/graph.py`](../src/schemas/graph.py).

Status values: `Todo` · `In progress` · `Done`. Update `Actual` and `Status` as each task lands.

## 0. Folder restructure (parallel, non-destructive)

Runs before any node in §1 is written. `src/core/` is left **completely untouched** for the whole
migration — every new file this plan writes goes straight to its new top-level path below, never
into `src/core/langgraph/`. `src/core/` is deleted in one commit only once every other milestone
here is `Done` (Milestone 11).

| Old | New |
|---|---|
| `src/core/configs/` | `src/configs/` |
| `src/core/observability/` | `src/observability/` |
| `src/core/llm.py` | `src/services/llm.py` |
| `src/core/langgraph/agents/` | `src/agents/` |
| `src/core/langgraph/nodes/` | `src/nodes/` |
| `src/core/langgraph/prompts/` | `src/prompts/` |
| `src/core/langgraph/runtime/` (incl. `runtime/backends/`) | `src/runtime/` (incl. `runtime/backends/`) |
| `src/core/langgraph/tools/` | `src/tools/` |
| `src/core/langgraph/verification/` (incl. `verification/deterministic/`) | `src/verification/` (incl. `verification/deterministic/`) |
| `src/core/langgraph/graph.py` | `src/graph.py` |

`graph.py` isn't a subfolder, but it's the only thing left inside `core/langgraph/` once every
subfolder above moves out — it has to go too, or `core/` never actually empties.

Everything not listed — `schemas/`, `enums/`, `constants/`, `services/*` other than `llm.py`,
`api/`, `models/`, `middlewares/`, `ui/`, `utils/`, `main.py` — stays exactly where it is.
`pyproject.toml` declares `packages = ["src"]` as a whole, so no packaging config changes are
needed for this.

Both trees exist side by side for the whole migration: the running app keeps depending on
`src/core/...` unmodified while the new tree fills in alongside it. **Don't edit anything under
`src/core/` in the meantime** — an edit there is silently lost at cutover, since cutover deletes
the folder rather than merging it.

`api/v1/*`, `main.py`, `middlewares/*`, `models/knowledge.py` and several `services/*` files
(`database`, `guard`, `knowledge`, `memory`, `preferences`, `profile`, `turn`) already import from
`src.core.*` today — every one of those import lines is what Milestone 11 repoints.

A milestone task that says "re-point" or "edit" a node (present in `core/langgraph/` already,
unchanged in this migration — e.g. `coach_agent`, `qa_agent`, `deterministic_verification`,
`present_plan`, `notify_fail`, `hitl_rejected_no_feedback`, `hitl_exhausted`, `qa_fallback`,
`verify_faithfulness`, everything under `prompts/`, `tools/`, `verification/deterministic/`,
`runtime/`) means: copy it to its new path first, then edit the copy. The old one stays in
`core/langgraph/` untouched, same as everything else in §0, until Milestone 11.

## 1. Node design

| Node | Purpose |
|---|---|
| `guard_input` | Unchanged — scan input, no LLM call |
| `blocked` | Unchanged |
| `supervisor` | LLM router, structured output (`next`) — a plain prompt for now, no explicit todo list (deferred, see §4) |
| `user_agent` | New. Tool-calling agent (`get_user_profile`, `update_user_profile`) — owns profile read/write end to end |
| `coach_agent` | Unchanged model call; now checks profile completeness itself before calling the LLM |
| `deterministic_verification` | Unchanged |
| `present_plan` | Unchanged rendering; now also stages `pending_approval` (`source="coach_agent"`) before routing to `hitl_agent` |
| `notify_fail` | Unchanged message; exits to `summarize` instead of `finalize_turn` |
| `hitl_agent` | Generalized from `hitl_review` — same interrupt/approve/reject/feedback/retry mechanics, but payload and decision are generic (`pending_approval`, `approval_decision`), shared by `coach_agent` and `user_agent` |
| `hitl_rejected_no_feedback` | Unchanged message; exits to `summarize` |
| `hitl_exhausted` | Unchanged message; exits to `summarize` |
| `commit_plan` | New. Only place a plan is persisted; reached only after `hitl_agent` approves a `source="coach_agent"` request |
| `commit_profile_update` | New. Only place an approved profile *overwrite* is persisted (a blank field is written directly by the tool, no approval needed) |
| `qa_agent` | Unchanged |
| `verify_faithfulness` | Unchanged |
| `qa_fallback` | Unchanged message; exits to `summarize` |
| `summarize` | New. Compresses `messages` past a threshold on a `HumanMessage` boundary; never touches any other state key |

### Removed

| Removed | Reason |
|---|---|
| `parse_turn` | Intent classification → `supervisor`'s own routing decision. Fact extraction → `user_agent`'s tool arguments; the model reads the conversation and calls `update_user_profile` directly, no separate NLU pass |
| `off_topic` | Folded into `supervisor`: an out-of-scope message is answered and routed straight to `FINISH` |
| `load_user_context` (node) | Folded into `user_agent`'s `get_user_profile` tool — loaded on demand, not unconditionally every turn |
| `merge_profile` | Folded into `user_agent`'s `update_user_profile` tool |
| `persist_profile` / `persist_preferences` | Folded into `update_user_profile` (blank field, direct write) and `commit_profile_update` (approved overwrite) |
| `check_profile_complete` | `coach_agent` computes this itself, on the fly, from `profile` — no state field for it |
| `request_missing_profile_fields` / `wait_for_user` | `user_agent` asks conversationally; no template node, no dedicated interrupt node |
| `profile_collection_exhausted` | Not carried over — see §4, no persistent nag-counter across turns |
| `finalize_turn` | Nothing left for it to do — persistence moved to `commit_plan` / `commit_profile_update`; the reply is the last `AIMessage` in the transcript |
| `hitl_review` | Renamed and generalized to `hitl_agent` |

## 2. Edge / routing design

| From | Condition | To |
|---|---|---|
| `guard_input` | blocked | `blocked` |
| `guard_input` | pass | `supervisor` |
| `blocked` | — | `END` |
| `supervisor` | `next = user_agent` | `user_agent` |
| `supervisor` | `next = coach_agent` | `coach_agent` |
| `supervisor` | `next = qa_agent` | `qa_agent` |
| `supervisor` | `next = FINISH` | `END` |
| `user_agent` | overwrite existing value | `hitl_agent` |
| `user_agent` | no change / blank field filled | `summarize` |
| `coach_agent` | — | `deterministic_verification` |
| `deterministic_verification` | pass | `present_plan` |
| `deterministic_verification` | retry | `coach_agent` |
| `deterministic_verification` | exhausted | `notify_fail` |
| `present_plan` | — | `hitl_agent` |
| `notify_fail` | — | `summarize` |
| `hitl_agent` | coach · approve | `commit_plan` |
| `hitl_agent` | coach · revise | `coach_agent` |
| `hitl_agent` | coach · no feedback | `hitl_rejected_no_feedback` |
| `hitl_agent` | coach · retry exhausted | `hitl_exhausted` |
| `hitl_agent` | user · approve | `commit_profile_update` |
| `hitl_agent` | user · reject | `user_agent` |
| `commit_plan` | — | `summarize` |
| `hitl_rejected_no_feedback` | — | `summarize` |
| `hitl_exhausted` | — | `summarize` |
| `commit_profile_update` | — | `summarize` |
| `qa_agent` | — | `verify_faithfulness` |
| `verify_faithfulness` | pass | `summarize` |
| `verify_faithfulness` | retry | `qa_agent` |
| `verify_faithfulness` | fallback | `qa_fallback` |
| `qa_fallback` | — | `summarize` |
| `summarize` | — | `supervisor` |

Only two edges in the whole graph reach `END`: `guard_input`'s block, and `supervisor`'s own
`FINISH`. Every other node returns to `supervisor` through `summarize`.

## 3. Supervisor prompt requirements (not a schema change)

- Prefer resolving read-only / non-blocking sub-requests (`qa_agent`) before a sub-request that
  ends in an approval interrupt (`coach_agent`'s plan, an overwrite through `user_agent`) — so a
  compound query isn't split across two user turns by an interrupt that lands first.
- Don't decide `FINISH` while any part of the original query is still unaddressed. No explicit
  `todos` list backs this yet (§4) — it is transcript re-reading only.

## 4. Known gaps, deferred on purpose

- No explicit `todos` / task-decomposition state. Supervisor re-reads the transcript each hop to
  decide what's left. Revisit if multi-intent queries turn out to be common enough that this drops
  a sub-intent in practice.
- No counter persists across turns if `user_agent` asks for a field and the user never answers
  (`user_info_retry_count` did this before). Within one turn, `iteration_count` still caps the loop.
- `approval_retry_count` is one counter shared by both the plan-revise loop and profile-overwrite
  rejections. If both happen in the same turn they share one retry budget.

## 5. Migration tasks

### Milestone 0 — Folder restructure scaffolding (0.5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Create the 9 new top-level packages listed in §0 (`__init__.py` only, empty) — `src/core/` untouched | 0.5 | 0.25 | Done |

### Milestone 1 — Foundation: state & enums (2.25h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Define new `GraphState`, `PendingApproval`, `ApprovalDecision`/`ApprovalSource`/`ApprovalKind`, `NextAgent`, `UserAgentContext` in `src/schemas/graph.py` | 1 | 1 | Done |
| 28/08 | Update `src/schemas/__init__.py` exports | 0.25 | 0.25 | Done |
| 28/08 | Add `Node` enum members: `SUPERVISOR`, `USER_AGENT`, `HITL_AGENT`, `COMMIT_PLAN`, `COMMIT_PROFILE_UPDATE`, `SUMMARIZE`; remove the ones §1 drops | 0.5 | 0.25 | Done |
| 28/08 | Add route literals for `supervisor`'s `next` and `hitl_agent`'s six outcomes in `src/enums/routes.py` | 0.5 | 0.25 | Done |

### Milestone 2 — Shared approval: `hitl_agent`, `commit_*` (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | `hitl_agent` node: generic `interrupt()`, reads `pending_approval.summary`, writes `approval_decision`/`approval_feedback`, increments `approval_retry_count` on reject + feedback | 1.5 | 0.5 | Done |
| 28/08 | `route_after_hitl`: dispatch on `pending_approval.source` + `approval_decision` (+ retry cap) to the 6 destinations in §2 | 1 | 0.25 | Done |
| 28/08 | `commit_plan` node: `save_plan(user_id, plan)`, compose confirmation message | 0.75 | 0.25 | Done |
| 28/08 | `commit_profile_update` node: apply the field(s) from `pending_approval.payload`, `save_profile`, compose confirmation message | 0.75 | 0.25 | Done |

### Milestone 3 — `user_agent` (3.5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | `get_user_profile` tool (read-only, wraps `load_user_context`) | 0.5 | 0.25 | Done |
| 28/08 | `update_user_profile` tool: write immediately when the field is blank; stage `pending_approval` (`kind="profile_update"`) when it would overwrite an existing value | 1.5 | 0.75 | Done |
| 28/08 | `user_agent` node (`create_agent` + the two tools, `UserAgentContext`) and its system prompt | 1 | 0.75 | Done |
| 28/08 | `route_after_user_agent`: `pending_approval` set → `hitl_agent`, else → `summarize` | 0.5 | 0.25 | Done |

### Milestone 4 — Coach branch rewire (2h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Add a profile-completeness precondition to `coach_agent` (reuse `missing_profile_fields`): skip the model call and return a "needs" note when required fields are missing | 1 | 1 | Done |
| 28/08 | `present_plan`: stage `pending_approval` (`kind="plan"`, rendered markdown as `summary`) before routing to `hitl_agent` | 0.5 | 0.5 | Done |
| 28/08 | Re-point `notify_fail`, `hitl_rejected_no_feedback`, `hitl_exhausted` from `finalize_turn` to `summarize` | 0.5 | 0.25 | Done |

### Milestone 5 — QA branch rewire (1h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Re-point `verify_faithfulness` (pass) and `qa_fallback` from `finalize_turn`/`END` to `summarize` | 1 | 0.75 | Done |

### Milestone 6 — `supervisor` & `summarize` (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | `supervisor` node: structured-output router (`next: NextAgent`), plain prompt per §3. Replaces the current `agents/supervisor.py` stub (a copy of `coach.py`) entirely | 1.5 | 1 | Done |
| 28/08 | `route_after_supervisor`: dispatch on `next` | 0.5 | 0.25 | Done |
| 28/08 | `summarize` node: threshold check, safe-harbor split on a `HumanMessage` boundary, LLM summary call, `RemoveMessage` pruning, append to `summary` | 1.5 | 1.25 | Done |
| 28/08 | `iteration_count` hard cap inside `supervisor` | 0.5 | 0.25 | Done |

### Milestone 7 — Graph assembly (2h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Rewrite `src/core/langgraph/graph.py`: new `NODES` tuple, new edges per §2 | 1 | 1 | Done |
| 28/08 | Rewrite `src/constants/routes.py` route tables for the new edges | 0.5 | 0.5 | Done |
| 28/08 | Delete the node/agent files §1 removes | 0.5 | 0.5 | Done |

### Milestone 8 — Dead code audit (1.5h)

Audited both files against the new pipeline (`src/agents/`, `src/nodes/`, `src/tools/`):
none of the four functions below, nor `parse_user_turn`/`ProfileStatement`/`TurnParse`/
`EXTRACTABLE_FIELDS`/`InjuryStatement`, have a caller there — `user_agent`'s
`update_user_profile` tool takes `field`/`value` straight from the LLM's tool call, one
field at a time, and never runs a turn-parsing or batch-merge step.

They are **not dead today**, though: this session found `src/core/langgraph/graph.py`
(and 10 of its node files) broken — deleted or import-broken by Milestone 7's commit
even though §0 requires `src/core/` to stay untouched and running until cutover. Restoring
that (see git history around 28/08 for the fix) means `parse_turn.py` and `merge_profile.py`
under `src/core/langgraph/nodes/` are live again, and they import exactly the symbols this
milestone targets (`parse_user_turn`, `TurnParse`, `DEFAULT_INTENT`, `ProfileStatement`,
`merge_profile_updates`, `pending_revision_fields`; `merge_injuries` and
`usable_profile_fields` are pulled in transitively through `merge_profile_updates`).
Removing them now reproduces the same breakage. Deferred to Milestone 11: they go with
the rest of `src/core/` in that cutover's delete, at which point this audit's conclusion
— dead to the new pipeline — becomes safe to act on without a compensating deletion.

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Audit `src/services/turn.py` (`parse_user_turn`, `ProfileStatement`, `EXTRACTABLE_FIELDS`) for continued use; remove if dead | 0.5 | 0.5 | Done — removed at the Milestone 11 cutover once `src/core/langgraph/nodes/parse_turn.py` was actually deleted; `turn.py` now holds only `PreferenceStatement` |
| 28/08 | Audit `src/services/profile.py` (`merge_profile_updates`, `merge_injuries`, `usable_profile_fields`, `pending_revision_fields`) for continued use; remove or fold into `update_user_profile` | 1 | 1 | Done — removed at the Milestone 11 cutover; no fold target existed since `update_user_profile` writes one field at a time, never a batch `ProfileStatement` |

### Milestone 9 — Docs (1.5h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Update `docs/state-design.md` to match the `GraphState` in §5 M1 | 0.5 | 0.5 | Done |
| 28/08 | Update `docs/implementation-plan.md` §1/§2 tables for the new topology | 0.75 | 0.5 | Done |
| 28/08 | Regenerate `docs/diagrams/*.mmd`/`.png`, or note in `implementation-plan.md` that `supervisor-workflow.html` is now authoritative | 0.25 | 0.25 | Done — noted; the three generated diagrams stay pinned to the old pipeline (`tests/test_graph_diagrams.py`) and retire with `src/core/` at cutover rather than being redrawn for the new loop topology |

### Milestone 10 — Testing (4h)

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Unit test `hitl_agent` + `route_after_hitl` for all 6 outcomes | 1 | 0.75 | Done — `tests/test_hitl_agent.py` |
| 28/08 | Unit test `update_user_profile`: blank-field direct write vs. overwrite staging | 1 | 0.5 | Done — `tests/test_update_user_profile.py` |
| 28/08 | Unit test `supervisor` routing decision + `iteration_count` cap | 1 | 0.75 | Done — `tests/test_supervisor.py` |
| 28/08 | Integration test: a compound query (QA + build plan) resolves both, QA first | 1 | 1 | Done — `tests/test_supervisor_loop.py`; profile seeded directly in state (see its `_ask` docstring — nothing between `supervisor`/`qa_agent`/`coach_agent` loads it on a fresh thread, only `user_agent`'s tools do) |

### Milestone 11 — Cutover: delete `src/core/` (1h)

Turned out much bigger than the estimate: the Milestone 0 folder restructure had only ever
moved the files each new-pipeline node/agent needed rewritten (`agents/`, most of `nodes/`,
`graph.py`). Everything those still depended on — `configs/config.py`, `observability/*`,
`llm.py`, `agents/history.py`, `prompts/{rendering,security}.py`, all of `runtime/` (incl.
`backends/`), all of `tools/` bar `profile.py`, all of `verification/` (incl.
`deterministic/`) — was still being imported live from `src/core/langgraph/` by files
already in the new tree. So this cutover also finished that restructure: moved those eight
subtrees with `git mv`, rebuilt every destination `__init__.py`, and repointed every
`src.core.*` import across the app (`api/`, `main.py`, `middlewares/*`, `models/knowledge.py`,
`alembic/env.py`, several `services/*`) and the test suite.

`src/runtime/facade.py` (moved from `src/core/langgraph/runtime/facade.py`) is the actual
cutover switch: it now imports `build_graph` from `src/graph.py` instead of
`src/core/langgraph/graph.py`, and `langgraph.json`'s `coaching_graph` entry points at
`src/graph.py:build_compiled_graph` — this is what makes the chat API and `langgraph dev`
run the new supervisor pipeline instead of the old fixed one. `src/observability/nodes.py`'s
`TRACKED_FIELDS` (what a trace records off each node's update) was still keyed on the old
schema's field names (`intent`, `hitl_decision`, `final_message`, …) and would have recorded
nothing useful for the new pipeline; updated to `next`/`approval_decision`/`approval_retry_count`
and dropped `final_message` (nothing produces an equivalent single field now — the reply is
the last `AIMessage`).

~30 test files that exercised old-pipeline-only nodes (`parse_turn`, `merge_profile`,
`hitl_review`, `finalize_turn`, `check_profile_complete`, `request_missing_profile_fields`,
`wait_for_user`, `profile_collection_exhausted`, `persist_profile`, the old `coach`/`qa`
agents, the old `graph.py` wiring/diagram tests) were deleted outright — their subject no
longer exists. A handful of mixed files (`test_guard.py`, `test_preferences.py`,
`test_load_user_context.py`, `test_security_block.py`, `test_node_observability.py`,
`test_graph_state.py`) had their old-pipeline-only tests removed and the rest repointed —
most of what they cover (`route_after_guard`, `stated_preferences`/`merge_entry`,
`missing_profile_fields`/`load_user_context` the service function, `security_block`, node
instrumentation, `GraphState` itself) is still very much alive.

`docs/diagrams/{workflow,coaching-flow,qa-flow}.{mmd,png}` and
`scripts/export_graph_diagrams.py` were deleted per Milestone 9's decision — they rendered
the old graph, and no equivalent exists for the new loop topology (see `implementation-plan.md`
§2). `docs/diagrams/rag-flow.png` is unrelated and stays.

| Date | Task | Est | Actual | Status |
|---|---|---|---|---|
| 28/08 | Repoint every `src.core.configs` / `src.core.observability` / `src.core.llm` / `src.core.langgraph.*` import (see §0's list — `api/`, `main.py`, `middlewares/*`, `models/knowledge.py`, `alembic/env.py`, several `services/*`) to the new top-level paths | 0.5 | ~2.5 (incl. finishing the Milestone 0 restructure — see above) | Done |
| 28/08 | Delete `src/core/` entirely (incl. `src/core/langgraph/routes.py`); strip the old `Node`/`STEP_LABELS`/schema entries; remove the now-dead symbols in `src/services/turn.py` and `src/services/profile.py` per Milestone 8; run the full test suite | 0.5 | ~2 (incl. ~30 obsolete test files removed, ~6 test files partially rewritten) | Done — 702 tests collect, 641 pass (`-m "not integration"`), 61 deselected |

**Total: ~27.75h estimated; Milestone 11 ran well over its 1h line once the unfinished
restructure surfaced — see its actuals above.**
