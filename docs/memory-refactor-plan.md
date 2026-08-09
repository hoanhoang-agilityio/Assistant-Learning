# Memory Refactor — Plan

Investigation of 2026-08-09, and the work it produced. The trigger: a user built
a plan in one conversation, opened another, asked *"what is my last plan"*, and
got back neither the plan nor anything about themselves.

Everything in the first section was measured against the running database, not
inferred from reading code. Session ids are real and can be re-checked.

---

## 1. What was actually wrong

### 1.1 The reported symptom

Session `854e6cd2` ("what is my last plan", 09:26:20) resolved to:

```
intent:  check          ← not general_qa
plan:    None
profile: {weight_kg: 73, age: 27, sex: male, goal: fat_loss, days_per_week: 4, …}
answer:  "I couldn't find a training plan in that message. Paste the plan — …"
```

Four independent causes, in order of how much each decided the outcome.

**Misrouting.** `classify.md` says *"A question about an existing plan that asks
for no change is `check`"*. But `check` means "the user pasted a plan, score it"
→ `_ingest_plan` finds no plan in the message → `ask_clarify_plan` returns a
constant. That branch reads no profile, no plan, and no memory of any kind, so
perfect memory would have produced the identical answer.

`DISPATCH_TARGETS` has six intents and none of them means *"show me what I
have"*. The question had no home.

**`RootState.plan` is session-scoped and never rehydrated.** It lives in the
checkpointer, keyed `thread_id = session.id`. `_snapshot` writes it to state
*and* to `plan_versions` — v7 exists, correctly linked to session `681c9452` —
but nothing loads the latest version back when a new session starts. The same
gap breaks `change_plan` in a fresh session (`patch_plan(state.plan or {}, …)`).
Only `revert` survives, because `_resolve_version` deliberately re-reads
`version_index` from Postgres.

**The profile was loaded but had no way out.** `general_qa` maps straight to
`qa`, skipping `load_profile`, and neither `QAState` nor `qa.md` has a slot for
the profile.

**Episodic memory is structurally one turn late.** `chatbot.py:41` claims idle
sessions and fires a background summary; `_graph_input` reads `recent_episodes`
concurrently in the same turn, filtering on `summary != ''`. Measured: session
`681c9452` was claimed at `09:26:20.034`, 22 ms after the new session was
created, and its summary landed after the read. With `EPISODIC_IDLE_MINUTES = 0`
this is not an edge case — the session the user just left is *always* summarised
too late for the turn that needs it.

### 1.2 What mem0 had actually stored

132 rows for user 1:

| Shape | Rows |
|---|---|
| `Assistant …` / `Findings:` / `Verdict:` / `Nutrition targets:` | 50 |
| Exercise dumps (`Upper A includes … 4x6-8 RIR 1-2`) | 38 |
| Dropped slots, observation dates, medical disclaimers | 29 |
| Macro dumps | 2 |
| Sentences beginning `User …` | 13 |

Of the 13, about 7 are *"User asked …"* — episodic, not standing facts. Filtering
out everything that duplicates a `user_profile` column leaves 16 rows: 4 episodic,
8 lines of **generic knee-rehab advice**, 3 verify/disclaimer/turn-state, 1 macro
dump.

**Standing qualitative user facts: zero.**

Three consequences worth stating separately.

*mem0 was feeding on its own failures.* Re-running the search for
`"what is my last plan"` returns, in slot 1, a memory written by that same failing
turn. Each retry writes another copy and occupies another slot.

*mem0's dedupe could not fire.* Every turn phrased the same fact differently
(`Upper A includes …` / `Upper A exercises include …` / `Upper A plan includes …`),
so each landed as a fresh ADD. That is also why *"aiming to reach 70 kg"* and
*"aiming to reach 75 kg"* both survive — precisely the class of fact that belongs
in a typed column.

*mem0 was writing into domain knowledge.* The eight knee-rehab lines are not
facts about anyone; they are generic training guidance, which `memory.md` declares
is configuration whose authority is git. mem0 opened a runtime write path into it,
storing model output as though it were curated knowledge. The next question about
knees would draw on both `search_knowledge` (seeded, reviewed) and its own earlier
generation, through one prompt, indistinguishably.

### 1.3 The naming was a category error

Long-term memory divides into semantic and episodic. The field named
`long_term_memory` sat as a sibling of `episodic_context` while naming their
shared parent — so any newly invented kind of durable fact looked like it
belonged there. `docs/memory.md` already used the correct labels
(`Semantic — user`, `Episodic`); only the code never followed.

---

## 2. Decisions

**2.1 The QA branch moves *inside* the profile gate, and the graph becomes one
spine.** Every turn passes `classify → load_context → extract_profile →
check_required` and branches exactly once, at `intent_branch`.

This reverses the first draft of this decision, which kept `dispatch → qa`
untouched on the grounds that a gate in front of QA would block medical and pain
questions pending data collection. Measured against the code, that argument does
not describe what is there: `REQUIRED_FIELDS["general_qa"]` is `()`, so
`check_required` computes an empty `missing` for QA and always reaches
`intent_branch`. The gate is a no-op on that path.

What the move buys is the thing §1.1 could not otherwise fix. Loading the
profile is not enough — the profile must also absorb what the user said *in this
message*. *"I'm 73 kg now, how much protein?"* answered from the stored row is
answered with the old weight. Running `extract_profile` before the branch makes
that turn correct, and deletes the background-extraction phase this plan
previously needed to compensate.

The gate invariant comes out stronger, not weaker: `check_required` is still the
only node with an edge to `intent_branch`, and `intent_branch` is now the only
way to reach *any* terminal branch, `qa` and `decline` included.

**2.2 Every memory layer loads in `load_context`, a node. The facade stops
assembling context entirely.** Profile, latest plan, `semantic_context` and
`episodic_context` are read in one place, once per turn.

Not a tool: two of the three are single-row lookups on a unique index, the third
a small indexed scan — low single-digit milliseconds together. A tool would make
the model spend an entire extra round-trip deciding whether to spend that, the
gate costing several hundred times the thing it gates.

Not the facade either, which was the first draft of this decision. The argument
against a node was one checkpoint write per turn (measured: 1244 checkpoints,
~3.7 KB per blob, ~96 per session), but 2.1 puts a node on that spot regardless.
The write is already paid, so every additional field in the same `update` is
free — which is what removes the reason to split the layers across two places.

Keeping it in the graph buys back two things a facade read gives up: the graph
stays self-contained, so a direct `ainvoke` — a test, LangGraph Studio, a future
entrypoint — gets real context instead of silently getting `{}` and `""`; and the
loads appear as a span in the trace rather than happening outside the root span.

`_graph_input` is left doing exactly one job: decide whether this turn starts a
run or resumes a paused one. That is what its docstring already says it is for.

The cost is that the reads serialise inside one node instead of running in the
facade's `asyncio.gather`. They can still be gathered *within* `load_context`, so
what is actually lost is overlapping them with `graph.aget_state` — single-digit
milliseconds.

**2.3 `long_term_memory` → `semantic_context`,** fed from `user_profile`. This
also makes a turn deterministic — no embedding, no top-k — which is the same
argument `episodes.py` already makes for chronological over semantic retrieval.

**2.4 mem0 is removed as a backend.** Its measured residual is empty, and every
category it held has an existing owner: `user_profile`, `plan_versions`,
`session.summary`, `knowledge_chunks`.

**2.5 `preferences` is not widened into a general fact store.** It is a single
TEXT column with replace semantics and one consumer. Using it as a bin recreates
the mem0 problem in a worse container: one string, no per-fact deletion, no
relevance filtering, injected whole on every call.

### Principles this produced

**The gate protects computation, not conversation.** `REQUIRED_FIELDS` exists
because `calc_macros` raises on a missing `activity_level` and `filter_candidates`
silently matches nothing without `level`. QA computes nothing. Medical and pain
questions must therefore never be blocked pending data collection — the safety
mechanism there is the prompt's scope limit and its escalation sentence, and the
advice that matters (stop the movement that hurts, see someone if it is sharp)
does not depend on body weight. Data collection belongs where an exercise is
actually prescribed, which is already gated.

Under 2.1 that principle stops being a property of the topology and becomes a
property of one tuple: `REQUIRED_FIELDS["general_qa"] = ()`. QA now walks through
`check_required`, so the emptiness is what keeps it walking. It is load-bearing
and must carry both a comment saying so and a test asserting it.

**A QA turn missing a field degrades; it does not ask.** `ask_missing` ends the
turn with a list of questions and no answer, which is right for `build_plan` and
wrong for *"how much protein?"* — that question has a real answer (1.6–2.2 g/kg)
that becomes a number as soon as a weight arrives. Answering and asking in the
same breath is one turn instead of two, and it is the reason the QA field check
belongs in `qa.md` rather than in `REQUIRED_FIELDS`.

**Tool when fetching is expensive or the query space is open; a node when it is
cheap and deterministic.** `search_knowledge` is a vector search over a corpus
and the agent genuinely cannot know in advance what it needs. `load_context`
always runs the same three queries, keyed on ids it is handed.

**Idleness is the wrong signal for "finished".** What episodic memory needs is
"stable since the last summary", which is a watermark comparison, not a timeout.

---

## 3. Work

### Phase 1 — One spine: gate every turn, load context inside it

Target topology:

```
START
 └→ classify            (LLM; writes intent / scope / changes, absorbs dispatch)
     └→ load_context
         └→ extract_profile
             └→ check_required ─┬→ ask_missing ──────────────────────→ finalize
                                └→ intent_branch ─┬→ qa ─────────────→ finalize
                                                  ├→ decline ────────→ finalize
                                                  ├→ planning
                                                  ├→ patch_plan
                                                  ├→ resolve_version
                                                  └→ ingest_plan → calc_macro → …
```

| File | Change |
|---|---|
| `app/services/versions.py` | Add `latest_version(user_id) -> PlanVersion \| None` |
| `app/core/langgraph/routing/classify.py` | Return `Command(update={…}, goto="load_context")`. Once the gate is hoisted, `dispatch` has one destination left and is dead weight |
| `app/core/langgraph/routing/dispatch.py` | Delete. `DISPATCH_TARGETS` and its mapping test move to `intent_branch`, which is now the only branch point |
| `app/core/langgraph/profile/nodes.py` | `load_profile` → `load_context`. One `asyncio.gather` over `get_profile`, `latest_version` and `recent_episodes`; then hydrate `plan` **and `macros`** — macros travel with the plan they were computed for — **only when `state.plan is None`**. Anonymous → `profile={}`, `episodic_context=""`, plan left alone |
| `nodes.py` | `recent_episodes(user_id: str \| None, exclude_session_id: str)` takes the raw `metadata["user_id"]` string, not the `int` that `_user_id` returns, and the session id from `configurable["thread_id"]`. Either pass both through or widen the signature — do not let `int` reach it silently |
| `nodes.py` `extract_profile` | Early return to `check_required` when `intent == "off_topic"`. The intent is known by now, and an off-topic message must not cost an extraction call or a profile write |
| `nodes.py` module docstring | The gate is the whole spine now, not a branch of it, and the module now owns context loading as well as the gate |
| `app/core/langgraph/graph.py` `_intent_branch` | Gains `general_qa → qa` and `off_topic → decline` |
| `graph.py` `_add_nodes` | Rewire per the diagram; `qa` and `decline` become destinations of `intent_branch` |
| `graph.py` `_graph_input` | Drop `memory_service.search` **and** `recent_episodes`; the gather collapses to `graph.aget_state`. The returned input is `{"messages": …}` and nothing else. Rewrite the docstring — it no longer reads memory layers |
| `graph.py` | Add `_render_semantic_context(profile)` beside `_render_plan_context`, plus `_SEMANTIC_LABELS` — `FIELD_LABELS` phrases the same columns as questions ("your height (cm)"), which reads as an interrogation in a list of things already known. Called from `_qa` and `_compose_answer`, at the point of use |
| `app/services/profile.py` | Comment on `REQUIRED_FIELDS["general_qa"] = ()` — it is now what keeps QA unblocked |
| `app/schemas/graph.py` | `long_term_memory` is **deleted**, not renamed. Semantic memory *is* `profile`; the rendered form is derived at the point of use. A copy in state would be written by `load_context`, before `extract_profile` merges this turn's facts, and would therefore always be one turn behind — which is the exact bug 2.1 exists to fix. `episodic_context` stays a field: it is loaded, not derived |
| `app/core/langgraph/agents/qa/state.py` | Same rename |
| `graph.py` call sites | `_qa` maps `semantic_context` into `QAState` and `_compose_answer` passes it to `load_system_prompt`; both now render it from `state.profile` rather than reading a state field |
| `graph.py` `get_response` | Drop `memory_service.add_in_background`. Scheduled for phase 3, pulled forward: removing the read while leaving the write in place keeps filling a table nothing reads |
| `app/core/prompts/__init__.py`, `system.md`, `qa.md` | Rename the slot; `qa.md` gains `{semantic_context}`. The two arg docstrings naming the root facade change to `load_context` |

Hydrating the plan only when `state.plan is None` is what protects a diff that is
staged but not yet approved: inside a session the checkpointer is the source of
truth and the database is the fallback for a session that has none.

The resume path needs no special handling once loading is a node. A thread parked
at an `interrupt()` resumes from the interrupted node, not from START, so
`load_context` does not run again and cannot overwrite anything the paused turn
was holding. The facade's `Command(resume=…)` early return used to be what
guaranteed this for the layers it seeded; that guarantee now comes from the
topology instead, which is one fewer thing to remember when editing the facade.

**Cost, stated plainly.** A QA turn now pays two serialised model calls before the
first streamed token — `classify` then `extract_profile` — where it previously
paid one. A parallel fan-out (`classify` alongside `extract_profile`, joining at
`check_required`) would make that `max()` rather than `sum()` at the price of a
deeper topology change; deferred, and worth revisiting with a measured TTFT
before and after.

### Phase 2 — Answer the recall question

| File | Change |
|---|---|
| `app/core/prompts/classify.md` | The `check` definition is restated as a condition on the **artifact, not the topic**: the plan has to be in the message. `revert` claims every question naming a version other than the current one, including "show me". `general_qa` gains the recall cases explicitly |
| `app/core/prompts/qa.md` | Two additions. Answer *about what they already have* straight from the rendered sections, day by day — this is the only place that question gets answered. And degrade rather than block: give the per-kg form and say what would make it specific. No longer optional — under 2.1 this is the *only* place a QA turn handles a missing field, because `REQUIRED_FIELDS["general_qa"]` stays empty by design |
| `tests/test_app_root_pipeline.py` | `pipeline` stubs `latest_version` and `recent_episodes` — `load_context` reads two stores the fixture previously left pointing at the real engine, so tests asserted against whatever was seeded locally |
| `tests/test_app_root_pipeline.py` | New: a `general_qa` turn in a fresh session rehydrates the saved plan and the plan, macros and semantic context all reach the QA prompt. Asserted on what the agent was handed, never on prose |
| `tests/test_app_root_pipeline.py` | New: a plan already in state is not overwritten by the database — rehydration is a fallback, not a refresh |

No `recall` intent and no `show_plan` node. `state.plan` is always the newest
saved version, so there is no separate "last" to fetch — a dedicated branch would
render the same object QA already holds.

Phase 1 does not make this phase unnecessary. `_ingest_plan` reads the pasted
message and writes `submitted_plan`; it never reads `state.plan`. So a hydrated
plan still does not reach the `check` branch, and *"what is my last plan"* routed
there still answers with `_NO_PLAN_FOUND_ANSWER`. The two phases only fix the
reported symptom together.

**What is still unverified.** The tests cover the wiring — given the intent, the
plan reaches the answer — not the classification itself. Whether the model
actually routes *"what is my last plan"* to `general_qa` lives in a prompt, on
the one node that steers control flow, and nothing in the repo can assert it. The
missing piece is a model-backed eval over at least: `"what is my last plan"`,
`"rate my split"` with no plan attached, `"review this: <plan>"`, and
`"show me last week's plan"`. Until that exists, a `classify.md` edit or a model
change can reroute turns silently.

**The capability this would have closed off, and how it was kept.** *"Is my plan
any good?"* with nothing pasted would otherwise reach QA, which discusses a plan
but cannot run the macro, volume and injury verifiers — leaving no path at all to
re-verify a saved plan. `_ingest_plan` now falls back to `state.plan`, which is
safe because `check` is in `READ_ONLY_INTENTS` and never reaches `snapshot`.

The condition is "nothing plan-shaped was found", not "`submitted_plan` is
empty". A message that carried a plan the parser could not read leaves
`unresolved` or `incomplete` behind, and reviewing a different plan in answer to
that would read as an answer to what they pasted.

### Phase 3 — Remove mem0

| File | Change |
|---|---|
| `graph.py` | Drop the import and `add_in_background` — done in phase 1, see the note there |
| `app/main.py` | Drop the import, `initialize()`, and `memory_enabled` from the startup log |
| `app/services/memory.py` | Delete |
| `app/core/configs/config.py` | Drop `LONG_TERM_MEMORY_*` |
| `pyproject.toml`, `uv.lock` | Drop `mem0ai>=2.0.15` and relock |
| `app/services/episodes.py` | Its module docstring contrasts episodes against mem0. The contrast still holds, against `user_profile` |
| `tests/test_app_memory.py` | Forced forward from phase 5: the module it imports no longer exists. Delete the mem0 block, keep the cache-degradation test, rewrite the header |
| `tests/test_app_memory.py` | `test_no_agent_searches_memory_for_itself` scans agents for `memory_service` — a string that can no longer appear, so the test can no longer fail. Repointed at `get_profile`, which is how the same rule gets broken now |
| `alembic/versions/b1c47e0a9f52` | New revision: `DROP TABLE IF EXISTS longterm_memory`, same for `mem0migrations`. `IF EXISTS` because mem0 created its tables lazily, so any environment where it never ran has neither |
| `alembic/env.py` | Both tables leave `EXCLUDE_TABLES` — after the revision there is nothing for autogenerate to propose dropping |

Stopping after `config.py` leaves the read and write paths dead but the
dependency and data intact, which is easy to undo. The migration is the point of
no return, and it is a separate `alembic upgrade head` — writing the revision is
not applying it.

Its `downgrade()` is deliberately empty. mem0 created those tables at runtime to
a schema this project never declared, and the dependency that knows that schema
is removed in the same change; recreating them would mean guessing at someone
else's DDL to produce empty tables nothing reads.

### Phase 4 — Episodic

| File | Change |
|---|---|
| `app/services/episodes.py` | Refreshable claim: `summarized_at IS NULL OR summarized_at < last_activity_at`, in both the candidate select **and** the conditional update. A one-shot claim means a session summarised at turn 2 of 20 never records the other 18, and its half-finished summary is frozen forever |
| `episodes.py` | `recent_episodes` orders by a correlated `EXISTS` over `plan_versions` before the date — the join already exists. Measured: 3 of 5 summarised sessions produced nothing and were crowding out the ones that did |
| `episodes.py` | `_newest_first`: selection is by preference, rendering is by date. Handing the model a history out of order invites it to call an old session the recent one |
| `episodes.py` | `_dedupe` before rendering, on normalised text, merging the plan labels of the copies it absorbs. Three near-identical protein lines were three real sessions four minutes apart, not a renderer bug |
| `config.py` | `EPISODIC_IDLE_MINUTES` 5 → 30 (the code default; no `.env` overrides it) |
| `tests/test_app_memory.py` | New: a stale summary is re-claimed, a settled one is not — the second half is what keeps a *failed* summary from costing a call every turn |
| `tests/test_app_memory.py` | New: with room for two, the session that produced a plan beats the more recent one that did not, and still renders last by date |
| `tests/test_app_memory.py` | New: identical summaries collapse to one line and the survivor keeps the absorbed session's plan label |

Seven sessions predating the migration have `last_activity_at = NULL` and can
never be claimed, since `_claim_stale_sessions` requires `IS NOT NULL`. Historical
data; left alone deliberately.

The refreshable claim changes what "never retried" means, and the narrower
meaning is the one that was wanted: a failed summary is not retried *for the same
content*. New turns in that session make it eligible again, which is correct —
there is something new to summarise — and a session nobody returns to still costs
exactly one call, forever.

Re-summarising is not free: a long-running conversation can now be summarised
several times over its life. `EPISODIC_IDLE_MINUTES = 30` is what bounds that,
and it is why the two changes belong in the same phase.

### Phase 5 — Tests, docs, data

| File | Change |
|---|---|
| `tests/test_app_memory.py` | Delete the mem0 block (fake client, signature, isolation — roughly lines 19–212); rename in the structural assertions. **Keep** the test asserting `episodic_context` is withheld from `compose_answer` |
| `tests/test_app_graph_routing.py:24,149,306` | `DISPATCH_TARGETS` no longer exists. The exhaustiveness assertion (`set(map) == set(Intent.__args__)`) moves to `intent_branch`'s own mapping; the write-intents assertion at :306 becomes "every write intent leaves `intent_branch` only through `check_required`" |
| `tests/test_app_graph_routing.py:117–122` | The monkeypatched `fake_load_profile` becomes `fake_load_context`, patching `app.core.langgraph.profile.nodes.load_context`, and must seed `plan` and `episodic_context` as well as `profile` |
| `tests/test_app_graph_routing.py:162,228,277` | `added == {"plan_context", "semantic_context", "episodic_context"}`; the two seeded `"long_term_memory": ""` fixtures rename |
| `tests/test_app_graph_routing.py` | New: topology is the single spine — `check_required` is the only edge into `intent_branch`, and `intent_branch` is the only edge into `qa` and `decline` |
| `tests/test_app_graph_routing.py` | New: `REQUIRED_FIELDS["general_qa"] == ()`, asserted directly — QA passes through the gate and this is what keeps it unblocked |
| `tests/test_app_graph_routing.py` | New: `extract_profile` performs no model call and no write when `intent == "off_topic"` |
| `tests/test_app_graph_routing.py` | New: `_graph_input` returns `{"messages": …}` only — a regression here would silently reintroduce facade-side context loading |
| `docs/memory.md` | `Semantic — user` is `user_profile` alone, with a short record of what mem0 actually held and why it went; the refreshable claim and the two retrieval adjustments; "no semantic search over history" replaces the mem0 entry under "Known limits" |
| `docs/workflow.md` | State definitions, the topology diagram, the node tables, §1.2 (one spine, one branch point), §9.4 (QA passes the gate and is never held there; it degrades rather than asks), §10.1, §12 |
| all of `app/` and `tests/` | Strip every `§` cross-reference from docstrings and comments. 61 of them across 17 files, some load-bearing for a reader who does not have `workflow.md` open — each rewritten to say the thing rather than cite where it is written down. `§` survives only inside `docs/` |
| database | Nothing left to do — `DROP TABLE` in phase 3 took the 132 rows with it |

---

## 4. Deferred, with reasons

| Item | Why it waits |
|---|---|
| ~~`preferences` in `extract_profile.md`, and fixing its merge~~ | **Done.** The merge turned out to be a live bug rather than a missing feature: `preferences` went through the same `{**stored, **extracted}` replace as `weight_kg`, so the first preference the extractor ever emitted would have silently erased the rest. `merge_preferences` accumulates with dedupe and a cap of 12, and the merge runs inside `upsert_profile` against a locked row, so two concurrent turns cannot lose one. `choose_exercises` needed no wiring at all — it already reads `profile["preferences"]`; the column was simply always empty |
| `recall` intent, `show_plan` node | No additional data to fetch |
| A `user_facts` table | Only once something needs to *address* one item — delete it, date it, ask which session it came from. `merge_preferences` and `_render_semantic_context` are the two seams the storage swaps behind. And if it is ever built, it should be typed rows the catalog filter can use (`avoid_exercise: burpee`), not prose — a free-text fact table is mem0 rewritten by hand |
| Time-range lookup tool (*"what did I train in May?"*) | This is the shape that genuinely earns a tool |
| Episodic rollup, tiered retention, TTL | After Phase 4 has run |
| ~~Surfacing `_unmapped_injury_notes` on a QA turn~~ | **Done, but not by surfacing it.** The note's wording is about a plan, so it is noise on a question about creatine and nagging if appended unconditionally. `unmapped_injury` was already reaching QA inside `semantic_context`; what was missing was a rule in `qa.md` telling the model to use it. The note itself is now skipped for `general_qa` and `off_topic`, where it was being computed and discarded |
| A `qa_needs` field on `IntentDecision` | The honest way to make QA field checks deterministic without keying them on intent: `classify` already reads the message and already pays for the call. Only once `qa.md`'s degrade wording proves insufficient |
| Parallel `classify` ∥ `extract_profile` | Recovers the TTFT that Phase 1 spends. Wait for a measurement that says it matters |

If `preferences` is later populated, the merge must be **deterministic** — the
extractor emits only the newly stated preference, and Python appends with dedupe
and a cap. Feeding the accumulated string back for a model to rewrite each turn
trades a loud bug for a quiet one. The realistic size of this field is a handful
of items; it converges, so a hard cap suffices and no compaction is needed.

`profile_hash` already excludes `preferences` — it steers exercise choice but
changes no number, so it must not invalidate a stored verify report. That is
already correct and should stay.

---

## 5. Notes

No schema migration in phases 1, 2 and 4. The only database work is revision
`b1c47e0a9f52` in phase 3, which drops both mem0 tables and with them the 132
rows — so the row deletion that phase 5 listed separately is already done by it.

Latency for a QA turn moves in both directions and the net is not assumed.
Removing mem0 drops an embedding call (~100–300 ms); `load_context` gathers three
indexed queries (~2 ms) in its place. Routing QA through the gate adds
`extract_profile`, a `gpt-5-mini` call, serialised before the first streamed
token — that is the one term that grows, and it dominates the other two. Measure
TTFT on the QA path before and after; if it regresses, the deferred fan-out is
the fix, not a retreat from the single spine.

The phases are ordered so each one leaves the system working. Phase 1 alone
changes no answer the user sees for the reported symptom — it makes the context
available; Phase 2 is what spends it. Phases 3–5 are independent of both and can
slip without blocking anything.
