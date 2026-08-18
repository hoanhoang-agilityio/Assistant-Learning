# Fitness Agent — domain rules

What a plan is, what makes one acceptable, and which of those rules a model is
allowed near. This is the reference for the **content**: the plan and catalog
shapes, the profile gate, the three rubric checks, the confirm rules, storage
and the injury policy.

**Orchestration is not here.** Who calls what, in what order, and why the order
is a model's decision rather than a graph's is
[`docs/supervisor-architecture.md`](supervisor-architecture.md). Memory layers
are [`docs/memory.md`](memory.md); auth is
[`docs/authentication.md`](authentication.md).

---

## 1. Three principles

**1.1. The LLM does not invent numbers.** Sets, reps, RIR come from the template;
calories and macros come from a formula. The model may only *choose* from a
pre-filtered list, so the hallucination surface collapses to one decision: "among
these 8 legal exercises, which one?"

**1.2. Control flow is not a tool.** A step the model may decide to skip is a
step that will be skipped. Steps that must run every turn are **middleware**,
which compiles to nodes the model cannot route around; steps that are conditions
on proceeding are **preconditions inside tool bodies**, returning a refusal the
model can read but not argue with. Nothing mandatory is exposed as a tool the
model chooses to call.

**1.3. The verifier is blind to how the plan was built.** It receives
`(plan, profile, macros, catalog, rubric)` — never `messages`. Enforced by
signature: `score(plan, profile, scope)` in `app/core/langgraph/verification/scoring.py` has
no argument a transcript could arrive in.

---

## 2. Shapes

### 2.1. Plan

Produced by `commit_draft`, stored in `plan_versions.plan`, and the input to
every check.

```json
{
  "template_id": "upper_lower_4day",
  "days": [
    {
      "name": "Upper A",
      "exercises": [
        {
          "slot_id": "ul4_horiz_push",
          "exercise_id": "bb_bench_press",
          "name": "Barbell bench press",
          "sets": 4,
          "reps": [6, 8],
          "rir": [1, 2]
        }
      ]
    }
  ]
}
```

A malformed plan reaching a check is a bug upstream, so the checks degrade to an
`info` issue naming what could not be assessed rather than crashing the turn.

### 2.2. Catalog entry

Keyed by `exercise_id`. `contribution` is what makes set counting honest, and
`joint_actions` / `loaded_positions` are what injury rules match on — never the
name.

```json
{
  "bb_bench_press": {
    "name": "Barbell bench press",
    "movement_pattern": "horizontal_push",
    "joint_actions": ["shoulder_horizontal_adduction", "elbow_extension"],
    "loaded_positions": ["shoulder_end_range_external"],
    "contribution": {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
    "equipment": ["barbell", "bench"],
    "skill_level": 2,
    "fatigue_cost": 3
  }
}
```

### 2.3. Issue and the envelopes

```python
class Issue(TypedDict):
    source: VerifyScope            # "macro" | "volume" | "injury"
    severity: Literal["info", "warn", "block"]
    location: str                  # "Push A / Barbell back squat"
    message: str
    suggestion: dict | None        # a replacement, not just a complaint
    rubric_ref: str                # "volume.quads.mrv" — traceable to the rule
```

`suggestion` carries a fix so a repair attempt has something to act on;
`rubric_ref` is what makes a verdict explainable months later against a stored
`rubric_version`.

Tools return one of five envelopes, all in `app/schemas/graph.py`:

| Envelope | Returned by | Carries a `draft_id`? |
|---|---|---|
| `DraftEnvelope` | `commit_draft`, `restore_version` | **Yes** — the handle `save_plan` needs |
| `ReviewEnvelope` | `score_plan` | **No**, deliberately — a review cannot become a saved plan |
| `MissingFields` | any tool whose profile precondition failed | — |
| `ToolRefusal` | any other declined precondition | — |
| `SavedVersion` | `save_plan` | — |

The plan JSON never travels through the supervisor's context; only the handle
and a rendering do. That is what stops a model retyping a set count on the way
to storage.

---

## 3. The profile gate

`REQUIRED_FIELDS` in `app/services/profile.py` is a **constant, per intent**, not
a model's judgment. Given the choice, a model eventually decides a profile looks
complete and proceeds with `activity_level = None`, producing a TDEE that is
wrong by several hundred calories and looks authoritative.

| Intent | Required |
|---|---|
| `build_plan`, `change_plan` | weight, height, age, sex, activity level, days/week, equipment, injuries, goal, level |
| `check` | weight, height, age, sex, activity level, injuries — the body data the macro and injury checks read, not the programme-shaping fields |
| `revert` | none |
| `general_qa` | **none, and load-bearing** |

`level` is required because candidate filtering compares against it. Left
unasked it defaulted to 1 — not a neutral default but the strictest possible
filter, dropping whole movement patterns without the user ever claiming to be a
beginner.

The empty tuple for `general_qa` is what stands between *"how do I train around a
sore knee?"* and a form asking for the user's height. The gate protects
*computation* — `calc_macros` raises without an activity level — and a knowledge
question computes nothing. A QA answer missing a number **degrades**: it gives
the per-kg form and asks for the weight in the same breath rather than ending
the turn with questions and no answer.

Missing fields are asked for in **one** batched turn, using `FIELD_LABELS` — the
question says "how active your day-to-day life is" rather than naming a database
column.

---

## 4. Building a plan

Inside `planning_agent`, three tools (`agents/planning/tools.py`). The
boundaries are the design: *if the model runs the first step and skips the
second, is the result wrong?*

```
get_template_slots  →  get_exercise_candidates  →  commit_draft
 (template + slots        (the one choice)          (assemble + score +
  + candidates)                                      mint the handle)
```

### 4.1. `get_template_slots` — template selection and filtering, bundled

Templates are matched on `days_per_week`, `goal` and `level`, ordered by
`popularity`; five are seeded from `data/template_seed.json`. The template
already carries `sets`, `reps` and `rir` for every slot — **this is where set and
rep counts come from, not the model.**

Candidate filtering rides along because a slot list without candidates is
useless and filtering is not a decision. Four filters, none advisory
(`services/catalog.py`):

* movement pattern matches the slot
* the exercise's equipment ⊆ what the user has
* skill level ≤ the user's level
* no joint action or loaded position is contraindicated by a declared injury

Empty result = conflicting constraints to report, never permission to relax a
filter. Candidates come back cheapest-fatigue first, capped at 8: the legal list
for a compound slot can run to thirty, and a model choosing from thirty spends
context it needs for the rest of the week.

### 4.2. `get_exercise_candidates` — the one place the model chooses

It picks one candidate per slot. Preferred over a random pick because it handles
what rules cannot: avoiding duplication across the week, balancing
barbell/dumbbell/machine, and honouring *"I hate deadlifts"*.

Injury filtering lives **inside** the tool, never in the prompt. A rule stated in
a prompt is a rule a model can weigh against something else.

`preferences` cannot influence the *split* — that comes from the template
library, matched on days, goal and level alone. A preference naming a programme
shape ("full body", "bro split") gets one explanatory line rather than silent
non-compliance.

### 4.3. `commit_draft` — assemble, score, mint

Assembles the JSON, hard-validates it (every `exercise_id` in the catalog, every
slot filled, sets/reps unchanged from the template), computes macros, runs the
three checks, and writes the result to the draft store. A validation failure is a
bug: it raises and logs rather than being reported to the user.

These four cannot be separated. A tool that returned a plan without having
verified it is a tool that will eventually be called on its own — and
`commit_draft` is the only path that mints a `draft_id`.

### 4.4. Changing a plan

Same agent, `mode="change"`. The delta is merged into the existing JSON
(`planning/patch.py`), keeping every constraint the plan already satisfied;
regenerating from scratch loses them. Adding a training day raises TDEE, which
moves the deficit — so macros and all three checks re-run. There is no shortcut
for a "small" change.

---

## 5. Reviewing a plan the user pasted

Reading the pasted text into structure is a `response_format=PastedPlan` call
that runs **before** the agent is invoked (`agents/review/transcribe.py`), not a
tool the agent reaches for. Transcription is mandatory, and a mandatory step
offered as a tool is one the model can decline — it did, and answered from its
own knowledge instead: no rubric, no macros, no injury check, and an answer that
read like a real assessment.

So `score_plan` takes **no arguments**. What was read arrives through
`ReviewState.submitted`, which leaves the model no argument to get wrong and no
way to skip the reading. The same move as `save_plan` having no `plan`
parameter.

Inside `review_agent`: `lookup_exercise` and `score_plan`
(`agents/review/tools.py`). The model decides what to report; it never decides
what an exercise *is*, and no longer decides what the user wrote.

`resolve_exercise` (`services/exercise_resolver.py`) is tiered, and every tier
reports a confidence:

| Tier | Rule | Confidence |
|---|---|---|
| 1 | exact match on the normalised name or the id | `1.0` |
| 2 | every meaningful query token appears in exactly one name | `0.8` |
| 3 | exactly one candidate once *style* qualifiers are discounted | `0.8` |
| 4 | several candidates that all four assessed fields agree on | `0.75` |
| 5 | character similarity, must clear the bar alone | the score itself |

Failing every tier it returns `exercise_id: None` plus the closest candidates.
**That is correct behaviour, not a failure.** Mapping "leg press" onto "leg
extension" does not produce a slightly-wrong review; it produces a confident
review of a plan the user is not doing, clearing a movement they never perform
and missing the one they do. `CONFIDENCE_THRESHOLD = 0.85` gates tier 5 only;
the tiers above it resolve on structure, and several sit below that number.

Tiers 3 and 4 exist because the catalog carries no canonical row per movement —
there is no "Bench Press", only four qualified variants — so the plainest names
a user can write matched several rows, none uniquely, and were reported as
unidentified. Neither tier guesses. Tier 3 discounts tokens that say *how* an
exercise is done (grip, tempo, machine) and keeps content words, so "Leg Press"
matches "Leg Press (Neutral Grip)" and not "Leg Press Calf Raise"; it needs a
query of two meaningful tokens, so a bare "press" stays a question. Tier 4
resolves several candidates only after proving they agree on `movement_pattern`,
`contribution`, `joint_actions` and `loaded_positions` — everything the checks
read — so the pick cannot change the review. Equipment and skill level are
excluded from that comparison deliberately: they gate what may be *planned* for
someone, not how a plan they already follow is assessed.

What tier 4 stands down on comes back in `equivalent`, and `score_plan` turns it
into an `info` finding (`ingest.variant_assumed`). The user is going to see
"Barbell Bench Press" where they wrote "Bench Press"; the note is what keeps
that from looking like a misreading.

Tiers 2 and 3 run in process over ~100 catalog rows. `pg_trgm` and pgvector are
the right answer at scale; neither extension is installed here, and the contract
callers depend on — `(exercise_id, confidence, candidates)` — does not change
when the backend does.

Lines that resolved are assessed; lines that did not are **reported, never
guessed**. A review that silently omits three exercises is worse than one that
names them. Sets and reps are never defaulted (a guessed set count is counted as
real volume); RIR is, because it affects no check.

`score_plan` returns a `ReviewEnvelope` with no handle. The distinction between
"a plan the user follows" and "a plan the user asked about" is that missing
field.

---

## 6. The three checks

Pure functions in `app/core/langgraph/verification/`, called by
`run_checks` in `app/core/langgraph/verification/scoring.py` — no graph, no model, no I/O.
Rubrics are seeded from `data/rubric_seed.json` into the `rubrics` table and
carry a `rubric_version` (currently `2026.2`) so an old verdict stays
reproducible.

`scope` narrows which checks run: `["injury"]` for a question about knee pain,
empty for anything that could be saved. An empty or unrecognised scope runs all
three — scoring nothing and reporting a pass is the one outcome that must be
unreachable.

Verdict: any `block` → `fail`; any `warn` → `warn`; otherwise `pass`. Warnings
never fail a plan — they are judgment calls the user is entitled to overrule.

### 6.1. `check_macro`

Reads `computed_macros` and `profile` against `macro_rules`:

```json
{
  "rubric_version": "2026.2",
  "protein_g_per_kg": {"min": 1.6, "target": 2.0, "max": 2.5},
  "fat_g_per_kg": {"min": 0.6},
  "deficit": {"max_pct_bw_per_week": 1.0, "max_pct_tdee": 25},
  "floor_kcal": {"male": 1500, "female": 1200}
}
```

Blocks on protein below the floor, fat below the floor, kcal below the
sex-specific floor, and a deficit deeper than 25% of TDEE — each with the
corrected number as a `suggestion`. Without body weight it reports that the
targets were **not assessed** rather than assuming one.

### 6.2. `check_volume`

Reads the plan and the catalog against `volume_landmarks`: fourteen muscle
groups, each with `mev` / `mav` / `mrv` and a cited `source`, plus:

```json
{
  "frequency": {"min_per_week": 2, "max_per_week": 3},
  "session":   {"max_sets": 25, "max_hard_sets_per_muscle": 10}
}
```

Sets are counted **fractionally** through `contribution`: one bench set is 1.0 to
chest and 0.5 each to triceps and front delts. Counting it whole for every muscle
it touches inflates every total and blocks plans that are fine.

Above MRV blocks (suggesting the top of MAV); below MEV warns — too little
volume is not dangerous. Frequency and session length warn. A muscle group with
no landmark, or an exercise missing from the catalog, produces an `info` issue
saying so: silence reads as approval. Muscles whose `mev` is 0 are exempt from
the frequency minimum — the rubric is saying they need no direct work, and
demanding a weekly minimum for them would contradict it.

### 6.3. `check_injury`

Reads the plan, `profile.injuries` and the catalog against `contraindications`:

```json
{
  "knee_pain_patellofemoral": {
    "severity": "block",
    "avoid_joint_actions": ["knee_flexion_deep"],
    "avoid_loaded_positions": ["knee_end_range"],
    "limit": [{"pattern": "lunge", "max_sets_week": 4}]
  }
}
```

**Injuries map to forbidden attributes, never to exercise-name lists.** Write
`"knee pain": ["squat", "lunge"]` and tomorrow `hack_squat` lands in the catalog
and slips through. As a set intersection over `joint_actions` and
`loaded_positions`, every exercise added later is graded correctly for free.

Pattern limits (`max_sets_week`) apply across the week, not per session. Each
block carries a safe alternative — one that does not carry the same
contraindication. An injury with no rubric entry is reported as **not assessed**;
a free-text injury the extractor could not map is stored as `unmapped_injury`
rather than guessed at.

Candidate filtering already excludes contraindicated exercises at build time, but
this check must still run: `patch_plan` and a pasted plan both introduce
exercises that never passed that filter.

---

## 7. When to stop trying

The repair loop is the planning agent's own loop, capped by middleware rather
than by a counter in state:

| Limit | Value | Behaviour |
|---|---|---|
| `commit_draft` calls | 3 | `continue` — the agent reports what is unresolved |
| `get_exercise_candidates` calls | 12 | `continue` — one failed check can name several slots |
| model calls (planning) | 17 | `end` — a floor under a model that only ever calls tools |
| model calls (supervisor) | 8 | `end` — a two-intent turn legitimately runs three or four hops |

Two or three failed attempts usually means genuinely conflicting constraints —
six days a week, bands only, both knees painful — and that is a decision for the
user. An uncapped loop turns it into a timeout.

---

## 8. Confirm rules

| Action | Confirm? | Reason |
|---|---|---|
| Build a plan | No | Nothing is overwritten until `save_plan` |
| **Save a plan** (`save_plan`) | **Yes** | The only write to `plan_versions` |
| Review a pasted plan | No | Read-only, and mints no handle |
| Knowledge question | No | Read-only |
| Off topic | No | Declined before the agent loop starts |

The gate is `HumanInTheLoopMiddleware`, interrupting on the **tool name**
`save_plan` — not on a model's judgment about whether a change is significant.
`interrupt()` freezes state at the pause point, so "yes" resumes the run that
staged the plan rather than rebuilding one from the transcript. Only `approve`
and `reject` are allowed decisions: an `edit` could hand back a different
`draft_id`, which is exactly the substitution the draft store exists to prevent.
Anything that is not a recognised yes is a no, and leaves the stored plan
untouched.

The question the user sees is rendered from the **draft** — its diff, its
rendering, its findings — never from the model's tool-call arguments.

### 8.1. The topic gate

`off_topic` is the one classification with nothing behind it: the gate writes a
constant and ends the turn before the agent loop starts, so no model call and no
tool. It reuses the classifier the turn was paying for anyway — a separate
guardrail would add a round-trip to every turn to catch the rare one — and it is
deliberately **not** the fallback when classification fails. That stays
`general_qa`: a classifier that just errored has made no judgment, and turning a
model outage into a refusal aimed at the user is the worse failure.

The boundary is narrow on purpose. Pain, injury, supplements, sleep and body
composition are in domain and answered as training questions, with a plain
statement that this is not a diagnosis. That disclaimer lives in the QA agent's
prompt, which is where the model that answers reads from.

---

## 9. Versions and revert

**A restore is append, not rewind.** Restoring v1 creates v4 carrying v1's
content, with `restored_from = v1` and `parent_id = v3`. v2 and v3 stay — delete
them and the user cannot undo the undo, and they will need to.

**A restored plan is always re-verified.** The old verdict is not reused: between
v1 and now the user may have lost 3 kg, or declared knee pain that did not exist
then, and a blind restore returns a plan that was once valid and is now
contraindicated. `profile_hash` is not used to *skip* the checks — they are pure
functions over data already in memory — but to tell the user *which* case they
are in: "your details are unchanged, so the same checks apply" or "your details
have changed, so it was checked again".

**The diff is shown against the current plan**, not the target. Users care about
what they are about to lose:

> Reverting to v1 (4 days, PPL). Dropping: day 5, the shoulder volume cut from
> v3. Macros back to 2100 kcal (currently 2300).

`list_versions` renders the index deterministically — a model paraphrasing it
could drop or reorder the entry the user is trying to choose between — and
`restore_version` takes an id from that list. An id belonging to another user is
refused with the same wording as one that does not exist; saying so differently
would confirm it exists.

---

## 10. Storage

| Data | Where | Why |
|---|---|---|
| Exercise catalog (~100 rows) | Postgres `exercises`, GIN-indexed | Precise array/set ops, not semantic search |
| Template library (5) | Postgres `templates`, seeded from `data/template_seed.json` | Config; changes go through a reviewed diff |
| Rubrics ×3 | Postgres `rubrics`, PK `(name, version)` | A cited version must stay reproducible |
| User profile | Postgres `user_profile` | Semantic memory: standing, typed, undated facts |
| Plan snapshots | Postgres `plan_versions` | Immutable; `session_id` records which conversation produced it |
| Conversation state | LangGraph Postgres checkpointer | Keyed by `thread_id = session.id` |
| Session summaries | Postgres `session.summary` | Episodic memory — see `docs/memory.md` |
| Knowledge base | pgvector `knowledge_chunks` | Only for `search_knowledge`; source is `data/knowledge/*.docx` |
| Drafts | In-process TTL cache, 30 min | Derived state that must not outlive the decision it supports |

**Rubrics and templates are served from Postgres but authored in git.** They
decide which plans pass, so they are closer to code than to data, and the danger
of a table is that someone bumps quads MRV from 22 to 30 with one `UPDATE` — no
PR, no diff — leaving every stored verdict unexplainable. Two rules keep the
audit trail:

* `data/rubric_seed.json` and `data/template_seed.json` are the source of truth;
  rows are written only by `scripts/seed_config.py`.
* `rubrics` is keyed by `(name, version)`. Re-seeding a changed rule at an
  existing version is refused: bump `rubric_version` and the new document is
  inserted beside the old one, with `is_active` moving to it.

Embeddings are derived data and must be re-indexed when their source changes. No
exercise name exists only in a vector store.

---

## 11. Failure modes

| Situation | Handling |
|---|---|
| `resolve_exercise` below 0.85 | Report the line with candidates; never guess |
| Pasted line missing sets or reps | Report it; sets are never defaulted (RIR is) |
| Repair attempts exhausted | Stop, present the findings, let the user decide |
| No template matches (6 days + bands only) | Reported at `get_template_slots`, not left for the checks to discover |
| A slot no legal exercise fills | The slot is left out with a `warn` naming the constraint responsible (injury, or equipment and level); the session count that feeds TDEE is read off the plan, not the profile |
| `_validate` fails after assembly | Exception and log. A bug, not user error |
| Profile changes mid-conversation | `extract_profile` runs every turn; a restore re-verifies against the profile now |
| Goal stated vs goal implied | `implied_goal` never overwrites the stored goal — it makes the assistant ask instead of assuming |
| A prompt asked to state a fact it was not handed | The gap is filled, not noticed. Anything a prompt tells the model to state must appear in the data that prompt carries — a 5-day plan was once announced as 4-day because the number was not rendered into the text |
| New session with no plan in the checkpointer | `load_context` rehydrates `plan` and `macros` from the newest saved version, but only when state has none, so a draft awaiting confirmation is not overwritten |
| Draft expired before the user answered | `save_plan` refuses with a readable reason — a draft that old was checked against a profile that may have moved |
| A failing plan reaches `save_plan` | Refused there, not only when the answer is composed, listing every blocking finding. A `fail` verdict is never stored |
| Signed-out session saves a plan | It becomes what the conversation holds but no row is written — there is no user to own it |

---

## 12. On injury data

Self-reported "knee pain" is not a diagnosis. The contraindication table assumes
patellofemoral pain when it might be a meniscus tear — in which case the "safe
alternative" would still be wrong. Therefore:

* default severity is conservative; prefer removing an exercise over keeping it
* the answer must say this is an exercise adjustment, not clinical advice
* an injury that could not be mapped to a rubric key is stored verbatim and
  reported as unassessed — never approximated to the nearest key
* for acute injuries or escalating pain, do not propose a plan; recommend
  professional care
