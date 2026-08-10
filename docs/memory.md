# Memory

Four things in this application are called memory, and they answer four
different questions. Confusing them is how a plan gets announced with a number
that nothing computed.

| Layer | Question it answers | Where | Written by | Read by |
|---|---|---|---|---|
| Working | "what has been said in *this* conversation" | LangGraph Postgres checkpointer, `thread_id = session.id` | Every node, automatically | Replayed into `messages` each turn |
| Semantic — domain | "what is true about training" | `knowledge_chunks` (pgvector), `exercises`, `templates`, `rubrics` | `scripts/seed_*.py`, from `data/` | `search_knowledge`, the planner, the verifiers |
| Semantic — user | "what is true about *this user*" | `user_profile` | `extract_profile` | The profile gate; rendered as `semantic_context` |
| Episodic | "what *happened*, and when" | `session.summary`, `plan_versions` | Background summariser; `_snapshot` | `episodic_context` in state |

There is no fifth. Procedural memory — how the assistant does things — is not
learned at runtime; see the last section.

---

## Working memory

The checkpointer, keyed by `thread_id = session.id`. Everything a turn derives
and does not need again is cleared by `NEW_TURN` (`app/schemas/graph.py`), and
the QA agent's tool round-trip never reaches the root transcript at all.

**It stops at the session boundary.** That is not a bug — replaying every past
conversation into every new one would be both expensive and wrong — but it is
the reason the episodic layer exists.

## Semantic memory

Two halves with a hard line between them.

**Domain knowledge** is configuration. Its authority is git: `data/*.json` and
`data/knowledge/*.docx`, loaded into Postgres by the seeders, never edited in
place. `rubrics` is keyed by `(name, version)` precisely so a version cited by a
stored `verify_report` can never be rewritten.

**User facts** are `user_profile`, and only `user_profile` — one row per user,
every field nullable, built up across turns by `extract_profile`.
`REQUIRED_FIELDS` decides what must be present before an intent may proceed,
deterministically, never by a model's judgment.

There was a second store here, a mem0 pgvector collection for the free-text half
— that they travel most weeks, that their gym is busy at 6pm. It was removed
after being measured: 132 rows for one user, and not one standing qualitative
fact among them. What it actually held was model output echoed back (verdicts,
macro dumps, exercise listings), generic training advice that belongs to the
curated knowledge base, and duplicates its own dedupe could not collapse because
every turn phrased the same fact differently. Every category it carried already
had an owner.

So semantic memory is now typed columns read by primary key. No embedding, no
top-k, and therefore a turn that is reproducible. The rendered form a prompt sees
— `semantic_context` — is derived from the profile at the point of use rather
than stored: `extract_profile` merges what the user said *this turn*, so a copy
made any earlier is a copy that is one turn behind.

Qualitative preferences have a home waiting for them in `user_profile.preferences`.
It is not populated yet, and filling it is a new capability rather than a
regression to repair — the note in `docs/memory-refactor-plan.md` records what a
deterministic merge for it has to look like.

## Episodic memory

`app/services/episodes.py`. Standing facts are not the same as events: "they
train fasted" is a fact, "three weeks ago they dropped to 3 days for work travel
and the plan was rebuilt" is an episode, and only the second answers "what did I
change last time?".

**Writing.** A session summarises itself at the **end of every turn**, in the
background: the chat endpoints call `summarize_current_session` once the graph
has run, and the write lands a second or two later.

Idleness used to be the signal, and it made the layer structurally one turn late.
Measured before the change: a session claimed 22 ms after its successor was
created, its summary landing after that turn had already read. The read happens
once, in `load_context` at the top of a turn, so a write triggered anywhere
inside the same turn cannot win. Writing at the end of every turn puts a whole
user-typing-cycle between the two, and there is nothing left to guess about when
a conversation ended.

What it costs is one small-model call per turn where the sweep paid one per
session, most of them immediately overwritten. Bounded by
`EPISODIC_SUMMARY_MODEL`, `max_tokens=256` and a transcript truncated to 6000
characters, and paid off the request path.

**The sweep is now the repair path.** At the start of every turn it still claims
this user's *other* sessions that have been quiet longer than
`EPISODIC_IDLE_MINUTES`, and fires a background summary for each. What it
collects is a turn-end write that never landed — a failed model call, a stream
the client aborted, a worker that died holding the task.

The claim and the select are one `UPDATE`, so concurrent workers cannot both pay
for the same summary — the same pattern as `app/services/session_naming.py`. It
is **refreshable**: a session is eligible when it has never been summarised *or*
when it has been talked in since it was (`summarized_at < last_activity_at`). A
one-shot claim freezes a conversation at whatever turn the sweep happened to
catch — summarised at turn 2 of 20, the other eighteen never exist as far as the
next session is concerned.

The two writers do not pay twice for the same conversation. `summarized_at` is
written **with** the summary, and `last_activity_at` is touched at the start of
the turn, so a successful turn-end write leaves `summarized_at` ahead and the
sweep's predicate stops matching. A write that never landed leaves it behind, and
the sweep collects the session once it goes quiet. The sweep's own claim is still
written **before** the model is called, so a session it cannot summarise does not
cost a call on every later turn.

**Reading.** `recent_episodes` returns up to `EPISODIC_RECENT_LIMIT` sessions,
dated, with the labels of the plan versions each produced. Read once per turn by
`load_context` and passed down in state — no agent retrieves for itself.

Retrieval is **chronological, not semantic**. "Last time", "three weeks ago" and
"the one before that" are questions about *when*; a nearest-neighbour search
answers a different question. It is the same line `app/models/knowledge.py` draws
between pgvector and an exact query, and it keeps a turn reproducible.

Within that, two adjustments, both measured. Sessions that produced a saved plan
are **preferred** — 3 of 5 summarised sessions had produced nothing and were
pushing out the ones that had. And summaries that say the same thing are
**collapsed** to one line, keeping the plan label of the copies absorbed; three
near-identical lines about protein were three real sessions four minutes apart,
not a rendering fault. Selection is by preference, rendering is by date: a
history handed to a model out of order invites it to call an old session the
recent one.

**Relations without a graph store.** `plan_versions.session_id` links what a
conversation was about to what came out of it. A foreign key, not an inferred
timestamp window — a user with two sessions open would otherwise get a version
attributed to the wrong one.

The constraint is `ON DELETE SET NULL`, and the direction matters: `plan_versions`
outranks `session`. Deleting a chat must not delete the plan the user is training
on (`CASCADE`), and must not start failing because a plan points at it
(`RESTRICT`, the default). The version survives; only the link to a conversation
that no longer exists goes away.

### Where episodic context is allowed

| Prompt | Gets it | |
|---|---|---|
| `system.md` | yes | Under its own heading, never merged with `semantic_context` |
| `qa.md` | yes | For "what did I do before" questions |
| `compose_answer.md` | **no** | |

`_compose_answer` is excluded and must stay excluded. It once announced a 5-day
plan as 4-day, sourcing the number from free-text memory instead of the rendered
plan it was handed. Episodic summaries are a second free-text account of the
user's plan history; handing them to that same prompt is the same bug with more
material. `semantic_context` is still passed, and that is a different risk: it is
rendered from typed columns, so there is no prose account of a plan in it to
misread a day count from. `tests/test_app_memory.py` asserts the exclusion
structurally, because the failure is invisible in review — the prompt still
renders, and the wrong number still reads like prose.

The other mitigations: `session_summary.md` forbids stating any number at all,
and `EPISODIC_MEMORY_ENABLED=false` turns the layer off entirely.

## Procedural memory is static, on purpose

Prompts (`app/core/prompts/*.md`), rubrics and templates are how the assistant
does things, and nothing at runtime rewrites them. Rubrics and templates are
served from Postgres but authored in git (`data/rubric_seed.json`,
`data/template_seed.json`, written only by `scripts/seed_config.py`).

This is a choice, not a gap. A stored verify report cites a `rubric_version` and
a `profile_hash`; both exist so an old verdict can be reproduced. A reflection
loop that edited a rubric in place would make every previously issued report
unexplainable. If self-improvement is wanted, the shape that preserves the audit
trail is a proposed diff against the seed file for a human to review — not a
write path into the table.

## Known limits

* **There is no semantic search over history.** Retrieval is the last few
  sessions by date. "Did we ever talk about my shoulder?" cannot be answered if
  it was twenty sessions ago. The cheap shape for that, if it is wanted, is a
  pgvector column on `session.summary` plus a lookup tool — not a fact store in
  front of the profile.
* **Anonymous turns have no memory of any kind.** `user_id` is the isolation
  boundary for all three persistent layers, and pooling anonymous users under a
  shared key would show one stranger's details to another.
* **Every layer fails soft except isolation.** A dead cache, an unreachable
  Postgres on the episodic read — each costs personalisation and returns `""`.
  None of them may cost the user their answer.
