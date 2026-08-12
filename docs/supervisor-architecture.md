# Supervisor architecture — every branch as an agent

**Status: implemented.** This is the system that runs. The root graph has been
replaced by a supervisor agent, and every branch with a real decision to make is
an agent of its own.

`docs/workflow.md` is the reference for everything the conversion did not
touch: the plan and catalog shapes, the profile gate, the rubrics and what each
check asserts, the confirm and revert rules, storage, and the reasoning behind
each. Read the two together — that one is the *domain*, this one is the
*orchestration* and what the change to it cost.

Where the code lives, section by section: the draft store in
`app/core/langgraph/runtime/draft_store.py`, the supervisor in `app/core/langgraph/supervisor/`,
the agents in `app/core/langgraph/agents/`, and the one function that bundles
macros with verification in `app/core/langgraph/verification/scoring.py`.

---

## 1. What the conversion is, and what it is not

The system was already multi-agent before the conversion: `agents/__init__.py`
registered a package per branch, each with its own state, its own contract and
its own span name. What changed is not the number of agents — it is **who
decides the order they run in**.

| | Before | Now |
|---|---|---|
| Order of steps | Edges in a graph | A model, re-deciding after each result |
| Routing | `classify` → `INTENT_TARGETS` lookup | The supervisor's own tool choice |
| Mandatory steps | Guaranteed by topology | Guaranteed by tool bodies and middleware |
| `patch_plan` | A root node | Absorbed into `planning_agent` |
| `resolve_version` | A root node with its own LLM call | Absorbed into the supervisor |

Two root nodes disappeared entirely. Both for the same reason: they existed to
make a judgment the supervisor is already making anyway. `patch_plan`
shares every input and every output with the build path, so `mode="change"` is
one parameter rather than a second branch; `resolve_version` maps *"the original
plan"* onto a `version_id`, and the supervisor has already read the conversation
that phrase came from.

---

## 2. The translation rule

Every guarantee the old root graph made was expressed as an edge. An agent has
no edges to express them with, so each one has to land somewhere else. There are
exactly three destinations, and the choice between them is not stylistic.

Ask, for each pair of adjacent steps: **if the agent runs the first and skips
the second, is the result wrong?**

| Answer | Destination |
|---|---|
| Yes, and the two steps belong to one operation | **One tool body.** What was an edge becomes a function call inside a tool |
| Yes, and the step must run every turn regardless of what the agent does | **Middleware hook.** These compile to real nodes, so they cannot be skipped |
| Yes, and the step is a condition on being allowed to proceed at all | **Precondition inside the tool**, returning a refusal envelope |
| No | A separate tool is fine |

The rule is what produces the tool list. It is not a preference about
granularity: a tool that returns a plan without having verified it is a tool
that will eventually be called on its own.

### 2.1. Why `create_agent` and not `StateGraph`

An agent's internal graph is fixed: a `model` node, a `tools` node, and one node
per middleware hook, wired by `create_agent`. There is no `add_node`. Anything
that needs arbitrary nodes and edges is not an agent — it is a `StateGraph`.
Nothing here needs one: `verification` was the last candidate, and it turned out
to need plain functions instead (§8).

This is why nothing below describes "nodes" inside an agent. Deterministic work
lives in tool bodies as plain Python; work that must run every turn lives in
middleware.

---

## 3. Diagram

```mermaid
flowchart TD
    START([user turn]) --> BA

    subgraph MW["middleware — replaces the spine"]
        BA["before_agent<br/>topic_gate · load_context · NEW_TURN"]
        BM["before_model<br/>extract_profile"]
        DP["dynamic_prompt<br/>profile · plan · missing fields"]
        BA --> BM --> DP
    end

    BA -->|off_topic| OFF["jump_to end<br/>constant · never enters the loop"]
    OFF --> DONE([answer])

    DP --> SUP{{"supervisor<br/>model loop"}}

    subgraph TOOLS["supervisor tools"]
        PLAN["planning_agent<br/>build · change"]
        REV["review_agent"]
        QA["qa_agent"]
        LV["list_versions"]
        RV["restore_version"]
    end

    SUP -->|tool call| TOOLS
    TOOLS -->|envelope| SUP

    SUP -->|save_plan draft_id| HITL{"HumanInTheLoop<br/>interrupt"}
    HITL -->|declined| SUP
    HITL -->|approved| SNAP["snapshot<br/>writes plan_versions"]
    SNAP --> SUP
    SUP --> DONE

    subgraph INSIDE["inside planning_agent"]
        GTS["get_template_slots"]
        GEC["get_exercise_candidates"]
        LOOP{{"selection loop<br/>ToolCallLimit"}}
        CD["commit_draft"]
        VERI["assemble → calc_macro → checks<br/>deterministic · no messages"]
        GTS --> LOOP
        GEC --> LOOP
        LOOP --> CD
        CD --> VERI
        VERI -->|verdict fail| LOOP
    end

    PLAN -.-> INSIDE
    VERI --> DRAFT[("draft store<br/>draft_id")]
    DRAFT -.->|handle only| SUP
    DRAFT ==>|full content<br/>never through the model| SNAP

    classDef sup fill:#EEEDFE,stroke:#534AB7,stroke-width:1.5px,color:#26215C
    classDef absorb fill:#FAECE7,stroke:#993C1D,stroke-width:1.5px,color:#4A1B0C
    classDef det fill:#E1F5EE,stroke:#0F6E56,stroke-width:1.5px,color:#04342C
    class SUP sup
    class PLAN,LV absorb
    class VERI,OFF det
```

---

## 4. Supervisor

Replaces four nodes: `classify`, `intent_branch`, `verdict_gate`,
`compose_answer`.

### 4.1. State

```python
class SupervisorState(AgentState):    # messages comes from AgentState
    profile: dict
    plan: dict | None                 # what the user has — survives the turn
    macros: dict | None
    episodic_context: str
    current_version_id: str | None    # parent_id for the next snapshot
    intent_hint: Intent | None        # from the topic gate, advisory only
    missing_fields: list[str]
    goal_conflict: GoalConflict | None
```

Eight fields, down from twenty in `RootState`. Everything that vanished —
`draft_plan`, `computed_macros`, `submitted_plan`, `issues`, `verdict`,
`repair_count`, `pending_commit`, `scope`, `changes`, `revert_target` — was
derived within a turn, and derived state now lives in the draft store instead
(§9). What is left is exactly the set that must survive the turn boundary, which
is also why the `NEW_TURN` reset gets simpler rather than harder.

`intent_hint` is advisory and must stay that way. It is the topic gate's
classification, passed on so the supervisor does not re-reason from scratch; it
is not a routing instruction, because the supervisor may legitimately disagree
after reading a tool result.

### 4.2. Tools

| Tool | Returns | Notes |
|---|---|---|
| `planning_agent(mode, changes)` | `DraftEnvelope` \| `MissingFields` | Agent-as-tool |
| `review_agent(pasted)` | `ReviewEnvelope` | Read-only; no `draft_id` |
| `qa_agent(question)` | text | Agent-as-tool |
| `list_versions()` | the rendered index | Replaces `resolve_version`. Loaded fresh — a plan may have been saved in another session |
| `restore_version(version_id)` | `DraftEnvelope` | Re-verifies before returning; refuses an id belonging to another user in the same words as one that does not exist |
| `save_plan(draft_id)` | `SavedVersion` | The only tool that writes `plan_versions` |

`save_plan` takes **no plan argument**. That is the whole point of it: the
content comes from the draft store, so the numbers written to `plan_versions`
are the numbers that were verified, not a version the model retyped.

It is the only *tool* that writes. One other write happens outside the tool list
entirely: `extract_profile` merges this turn's stated facts into `user_profile`
on every model call. That is deliberate — the profile has to absorb *"I'm 73 kg
now"* before anything computes with it — and it is middleware precisely so no
model decides whether it happens.

Subagents are called as tools rather than handed control with
`Command(goto=...)`. Handoff would end the supervisor's turn, and the confirm
gate, the save and the final answer all live at supervisor level — nothing would
be left to run them.

### 4.3. Middleware

| Hook | Replaces | Runs |
|---|---|---|
| `before_agent`: `topic_gate` | `classify`, `decline`, `NEW_TURN` | Once per turn |
| `before_agent`: `load_context` | `load_context` | Once per turn |
| `before_model`: `extract_profile` | `extract_profile` | Every model call |
| `dynamic_prompt`: `supervisor_prompt` | `render_semantic_context`, `ask_missing`, `ask_goal` | Every model call |
| `HumanInTheLoopMiddleware(interrupt_on={"save_plan"})` | `build_diff` + `confirm` | On the save call |
| `ModelCallLimitMiddleware(run_limit=8, exit_behavior="end")` | `recursion_limit` | Every model call |
| `ModelRetryMiddleware`, `ModelFallbackMiddleware` | `llm_service` retry and fallback | On failure |

`ModelCallLimitMiddleware` is not the same guard as `recursion_limit`, which is
why it replaces it: a turn with two intents legitimately runs three or four hops,
and `end` stops cleanly with whatever has been written instead of failing the
turn with a stack trace.

#### The confirm gate

`HumanInTheLoopMiddleware` interrupts on the **tool name** `save_plan`, not on a
model's judgment about whether this change is significant. The old `confirm`
node could not be reasoned past, and neither can this one.

Two details carry the rest of it. The allowed decisions are `approve` and
`reject` only: `edit` would let the gate hand back changed arguments — a
different `draft_id` — which is exactly the substitution the draft store exists
to prevent, and `respond` would answer on the tool's behalf, which for a save
means telling the model a plan was stored when none was. And the question the
user sees is rendered from the **draft** — its diff, its rendering, its blocking
findings — never from the tool call's arguments beyond the handle. A question
assembled from what the model typed would be a question about a different plan
than the one about to be stored.

#### The topic gate

```python
@before_agent(state_schema=SupervisorState, can_jump_to=["end"])
async def topic_gate(state: SupervisorState, runtime: Runtime) -> dict | None:
    """Refuse an out-of-scope message before the supervisor ever sees it."""
    try:
        decision = await llm_classify(_conversation(state, CONTEXT_TURNS))
    except Exception as e:
        # A classifier that just failed has made no decision. Turning a bad
        # minute for the model into a refusal aimed at the user is the worse
        # of the two errors, so the turn proceeds with no hint.
        logger.exception("routing_classify_failed_hint_unset", error=str(e))
        return dict(NEW_TURN)

    if decision.intent == "off_topic":
        return {**NEW_TURN, "messages": [AIMessage(content=OFF_TOPIC_ANSWER)], "jump_to": "end"}

    return {**NEW_TURN, "intent_hint": decision.intent}
```

`classify` does not die in the conversion — it moves into this hook, and its
output is used for two things instead of one: the topic decision, and
`intent_hint`. That is what keeps the gate from costing an extra round-trip,
which is the objection `workflow.md` §8.1 raises against a standalone guardrail
and which still stands.

It must be ordered **before** the `extract_profile` hook. An off-topic turn
writes nothing to the profile, and that property now comes from ordering alone —
the gate ends the turn before the extractor ever runs.

`before_agent` is the right hook and `before_model` is not: the topic of a turn
does not change between iterations of the loop, so classifying on every model
call pays three times for one answer.

---

## 5. `planning_agent`

Absorbs the build branch and `patch_plan`. The one agent whose nature actually
changed: `choose_exercises` was a single structured call, and is now the agent's
own loop — it picks an exercise, commits, reads the verdict, and picks again.

### 5.1. State

```python
class PlanningState(AgentState):
    profile: dict
    goal: str
    preferences: str                  # extracted string, not a transcript
    mode: Literal["build", "change"]
    changes: dict                     # empty for build
    base_plan: dict | None            # the plan being changed; None for build
    base_macros: dict | None          # so commit_draft can diff without retyping numbers
    template: dict | None
    slots: list[dict]                 # each with its legal candidate list
    draft_id: str | None              # the agent's only real output
    notes: list[dict]                 # setup findings, carried into the envelope
```

No `plan` field, and no `draft_plan`. The agent cannot write the user's plan
because it has nowhere to write it: its only output is a `draft_id` minted by
`commit_draft`.

`slots` carries each slot's legal candidates, and that list is the one the model
must choose from — an id outside it is rejected at commit time, so a
contraindicated exercise cannot enter a plan even if the model names one.
`messages` exists only because `create_agent` requires it; it holds the agent's
own tool round-trip, not the user's conversation.

`preferences` stays an extracted string rather than a transcript: the reason an
exercise was chosen has to be traceable to a value in state, not to a sentence
somewhere in a transcript.

### 5.2. Tools

| Tool | Body contains | Why merged |
|---|---|---|
| `get_template_slots()` | `select_template` + `filter_candidates` | Candidate filtering is not a decision; a slot list without candidates is useless |
| `get_exercise_candidates(slot_id, exclude_ids)` | catalog query with injury filter applied | The one place the model chooses. Injury filtering is inside the tool, never in the prompt |
| `commit_draft()` | `assemble_plan` + `score()` (macros + checks) + draft store write | §2, first row. These cannot be separated |

`commit_draft` is the **only** way a plan this agent built acquires a `draft_id`,
and the supervisor accepts nothing else as a plan. An agent that assembles a plan
on its own and reports it has produced nothing the system will save. (One other
function mints — `restore_version` — and it must; see §9.)

### 5.3. Middleware

| Hook | Purpose |
|---|---|
| `dynamic_prompt` | Renders profile, mode, and the change delta |
| `ToolCallLimitMiddleware("commit_draft", run_limit=3, exit_behavior="continue")` | Replaces `_MAX_REPAIRS`. The repair loop is the agent's loop, so its cap moves here |
| `ToolCallLimitMiddleware("get_exercise_candidates", run_limit=12, exit_behavior="continue")` | Generous relative to commits: one failed check can name several slots, and each is a separate lookup |
| `ModelCallLimitMiddleware(run_limit=17, exit_behavior="end")` | Floor under a model that only ever calls tools |
| `ModelRetryMiddleware`, `ModelFallbackMiddleware` | Same registry order as `llm_service` |

`continue` rather than `end` on the tool limits: the agent is told it has
committed enough and gets to report what is unresolved, rather than the turn
dying on a limit the user did not cause.

The cap is not optional. `workflow.md` §7 stops after a few failed attempts
because repeated failure usually means genuinely conflicting constraints — six sessions a
week, bands only, both knees hurting — which is a decision for the user. An
uncapped loop turns that into a timeout.

---

## 6. `review_agent`

What `ingest` became. It earns agent status because the input is free text of
unknown quality and the number of resolution rounds cannot be predicted.

### 6.1. State

```python
class ReviewState(AgentState):
    catalog: dict
    profile: dict
    submitted_plan: dict | None       # what was understood — not a handle
    unresolved: list[dict]            # lines no catalog entry matched, with candidates
    incomplete: list[str]             # lines missing sets or reps
    scored: bool
```

It carries `messages`, unlike `PlanningState`: the plan being reviewed *is* what
the user typed, so reading the conversation is the job here.

### 6.2. Tools

| Tool | Body contains |
|---|---|
| `lookup_exercise(raw_text)` | `resolve_exercise` — exact, then token-subset, then character similarity. Returns a null match plus candidates below the 0.85 threshold |
| `score_plan(days)` | `score()` — macros + checks, read-only |

`score_plan` returns a `ReviewEnvelope`, which deliberately **has no
`draft_id`**. That is how `submitted_plan` is kept from becoming `plan`: a review
produces nothing `save_plan` can accept. The distinction between a plan the
user follows and a plan they only asked about used to need two separate state
fields; here it is the absence of a handle (`workflow.md` §2.3).

Low confidence from `resolve_exercise` is reported, never guessed. A review that
silently omits three exercises is worse than one that names them.

### 6.3. Middleware

`dynamic_prompt`, retry and fallback, then a `ToolCallLimitMiddleware` per tool
— 6 lookups, 2 scores — and `ModelCallLimitMiddleware(run_limit=10)` under both.
Same shape as the others.

---

## 7. `qa_agent`

Untouched by the conversion. `agents/qa/agent.py` was already `create_agent`
with five middleware and no nodes, which is why it is the reference the two
agents above were built against.

Two tools: `search_knowledge` and `estimate_macros`. The second answers a
what-if — *"what would 5 days do to my calories?"* — with a number instead of
the general form. It is safe here and **only** here, because QA is read-only and
has no path to a save; a test asserts it appears in no other agent's tool list.
It is documented as an estimate and forbidden for *"what is my current protein
target"*, which is answered by quoting `plan_context` verbatim — two different
numbers for the same question is worse than one general answer.

`QAState` has no `plan`, `draft_plan` or `macros` field. The plan arrives as
`plan_context`, a rendered read-only string, so a knowledge question cannot
mutate the plan even by mistake.

---

## 8. `verification` — not an agent, and no longer a graph either

It was a `StateGraph`: a conditional entry edge fanning out to `verify_macro`,
`verify_volume` and `verify_injury`, joined at `merge_issues`. It is now three
plain functions in `core/langgraph/checks/`, called in sequence by `run_checks`
inside `core/langgraph/scoring.py`. Same rules, same findings, same verdict —
`app/core/langgraph/agents/verification/` is gone.

The fan-out was the only argument for the graph, and it was not one. The checks
are arithmetic over dicts with no I/O, so running them as concurrent nodes on a
single event loop bought no parallelism; what it cost was a `VerifyState` that
had to be assembled at every call site, an `add` reducer on `issues`, a join
node whose whole job was `max(severity)`, a compiled-graph cache, and a
`merge_issues` docstring explaining why it must not write `issues` back. Six
mechanisms for `issues.extend(...)`.

What the graph enforced structurally survives, in a stronger form. `VerifyState`
kept the verifier blind to the build process by omitting `messages`; `score(plan,
profile, scope)` has no argument a transcript could arrive in at all. The
guarantee moved from a field that had to stay absent to a signature that would
have to grow a parameter.

Two things genuinely change. Verification no longer appears in Langfuse as its
own span tree — its findings are log lines inside the calling tool's span — and
`scope` no longer narrows work by pruning edges, it narrows it with an `if`.
Both were priced in: the trace still shows which tool scored what, and the
checks are cheap enough that skipping one saves microseconds, not a model call.

Giving a model any part of rubric scoring would make MRV and MEV negotiable.
They are not, which is why none of this is a tool.

---

## 9. The draft store

The single most important mechanic in the conversion. Without it, plan JSON
travels from a tool result, through the supervisor's context, and into the next
tool call — and the moment a model retypes a number, `workflow.md` §1.1 is dead.

```python
class DraftEnvelope(TypedDict):
    status: Literal["draft"]
    draft_id: str            # the handle — the only thing save_plan accepts
    plan_rendered: str       # text for the supervisor to describe, not to relay
    macros: dict
    issues: list[Issue]
    verdict: Literal["pass", "warn", "fail"]
    diff: dict | None        # None for build; the confirm question renders this
```

Rules, all of them load-bearing:

1. Two functions mint: `commit_draft` and `restore_version`. Both score first —
   `mint` has no default for `macros`, `issues` or `verdict`, so it cannot be
   called without them, and a test asserts both callers reach `score()`.
   A restore *must* mint rather than revive the old draft: it is re-verified
   against the profile as it stands now, which makes it a new draft.
2. `save_plan(draft_id)` reads the content from the store, never from arguments.
3. A draft with `verdict == "fail"` is refused at save time, not only when the
   answer is composed. A failing plan that reaches the store is a failing plan
   the user trains.
4. Drafts expire — a 30-minute TTL. A `draft_id` from three turns ago describes a
   profile that may have changed since, and `save_plan` says so rather than
   storing it.
5. `plan_rendered` is for prose. The supervisor describes the plan from it; it
   does not reconstruct the plan out of it.

`build_diff` folds into the envelope rather than being its own tool, because the
diff is what the confirm question shows and there is no moment when one is
wanted without the other.

---

## 10. What the profile gate became

It cannot be a tool. Given `check_profile()` as an option, some turns the model
will decide the profile looks complete and proceed with `activity_level = None`,
producing a TDEE wrong by several hundred calories that looks authoritative.
That is `workflow.md` §1.2 and it does not stop being true here.

So it becomes a precondition, checked on the first line of every tool that could
produce a plan:

```python
@tool
async def planning_agent(
    runtime: ToolRuntime, mode: str = "build", changes: dict | None = None
) -> Command:
    """Build or change a plan. The profile is read from state, never passed in."""
    profile = runtime.state.get("profile") or {}
    intent = "change_plan" if mode == "change" else "build_plan"

    refusal = _profile_precondition(profile, intent, runtime.state)
    if refusal is not None:
        return _refuse(runtime.tool_call_id, refusal, missing=refusal.get("fields"))
    ...
```

The precondition covers the goal conflict too: a turn that implies a different
goal than the stored one asks about it rather than silently planning for one of
them.

Two properties come from this, and both matter:

- Calling the tool anyway achieves nothing but a list of what to ask for.
- The tool does **not** accept `profile` as a parameter. A tool that did would
  let the model fill in `weight_kg=75` for a user who never said it.

`REQUIRED_FIELDS` stays a constant in `app/services/profile.py`. It is not the
model's judgment about whether it has enough information.

---

## 11. What was lost, and what replaced it

Three things. Stated plainly, because the design is only honest if they are.
Each replacement is in the codebase; none is still a plan.

### 11.1. `calc_macro` became local invariants instead of one global one

In the root graph no path from any plan to any answer could skip it, because
`calc_macro` was the only edge into `verification`. It is now guaranteed inside
`commit_draft`, `score_plan` and `restore_version` — separately. A fourth
plan-producing tool added later that forgets to bundle it would be a silent bug
of a kind the old graph could not have.

**Replacement, in place:** `score()` bundles macros and the checks into one call,
`drafts.mint` has no default for `macros`, `issues` or `verdict`, and
`test_every_minted_draft_carries_macros` asserts that both minting tools reach
`score()` first.

### 11.2. Topology tests became static and behavioural tests

`tests/test_app_graph_routing.py` *proved* properties by inspecting edges:
`test_no_intent_can_skip_the_profile_gate`, `test_only_finalize_ends_the_graph`,
`test_decline_cannot_reach_anything_that_touches_a_plan`. None of them ported,
and the file is gone.

**Replacement, in place:** the strongest available substitute is static, in
`tests/test_app_supervisor.py` — no subagent's tool set contains a write tool,
`save_plan` has no `plan` parameter, no plan-producing tool accepts a `profile`,
only `commit_draft` and `restore_version` mint a handle, every minted draft
carries macros, and nothing in the scoring path takes an argument a transcript
could arrive in. All six run without a model. What genuinely needs behaviour —
the confirm gate end to end — is `tests/test_app_turn.py`, which mocks a model
and samples: slower and weaker than an edge, and the honest price.

### 11.3. Trace shape stopped being deterministic

`evals/` baselines compare runs. A supervisor that takes a different number of
hops on the same input makes those comparisons noisier.

**Replacement, in place:** `evals/` scores outcomes rather than spans. The trace
mapper reads the supervisor's final output, and the domain judges
(`plan_safety`, `macro_consistency`, `confirm_discipline`, `verdict_grounding`)
grade what the turn produced, not the route it took to get there.

### 11.4. What is *not* lost

The topic gate (§4.3), the confirm gate (`HumanInTheLoopMiddleware` interrupts
on a tool name, not on a model's judgment), and verifier blindness (§8) all
survive intact. An earlier draft of this design listed the first as a casualty;
it is not.

---

## 12. Layout and registry

```
app/core/langgraph/
  graph.py              the facade the API calls; owns the checkpointer pool
  prompts/              shared .md: classify, extract_profile, session title/summary
  supervisor/
    agent.py            build_supervisor() — create_agent + middleware + HITL
    middleware.py       topic_gate, load_context, extract_profile, supervisor_prompt
    tools.py            planning_agent, review_agent, qa_agent,
                        list_versions, restore_version, save_plan
    state.py            SupervisorState, NEW_TURN
    prompts/            supervisor.md
  agents/
    __init__.py         AGENTS registry
    planning/           agent.py · tools.py · patch.py · state.py · prompts/
    review/             agent.py · tools.py · state.py · prompts/
    qa/                 agent.py · tools.py · state.py · prompts/
  routing/classify.py   the classifier the topic gate calls
  profile/extraction.py extraction cleanup and goal-conflict detection
  checks/               macro.py · volume.py · injury.py — pure functions
  scoring.py            score() — macros and the checks, together
  drafts/store.py       mint, read, expire
  diff.py               what a save is about to change
  versioning.py         the version index, and what a restore re-checked
  rendering.py          every string a model may see about a plan
  models.py             model choice + retry/fallback middleware
```

`agents/planning/nodes.py` is gone. Its four functions did not disappear —
`select_template` and `filter_candidates` became the body of
`get_template_slots`, `assemble_plan` became part of `commit_draft`, and
`choose_exercises` became the model loop itself.

```python
AGENTS: dict[str, Callable[[], CompiledStateGraph]] = {
    "planning": build_planning_agent,
    "review":   review_agent,
    "qa":       qa_agent,
}
```

Three names. `verification` left the registry when it stopped being a graph
(§8); what remains of it is `checks/` plus `scoring.py`, which no builder needs
to compile. The registry docstring still holds: `routing/` and `profile/` remain
outside it, now because they are middleware rather than because they are root
nodes.

---

## 13. What the decision rested on

A record of why this was done, kept because the reasoning outlives the
decision. **The symbols named below are the router's, and most no longer
exist** — `draft_plan`, `repair_count`, `_NO_PLAN_FOUND_ANSWER` and
`_UNBUILT_BRANCH_ANSWER` all went with it.

The case for a supervisor rested on three things the router could not do: handle
a turn with two intents, recover from its own bad routing decision, and ask a
follow-up without ending the turn. All three were measurable from Langfuse
traces rather than arguable:

- Share of turns where the classified intent produced nothing (`draft_plan is
  None`, `_NO_PLAN_FOUND_ANSWER`, `_UNBUILT_BRANCH_ANSWER`) — the misroute rate.
- Share of turns immediately followed by a user correction — the multi-intent
  need.
- Distribution of `repair_count == 2` — the self-correction need.

Below roughly 5% misroutes, a supervisor would not have paid for what §11 costs.
The intermediate option — keep the router and the spine, convert only `planning`
and `ingest` into agents, leave `calc_macro`, verification and `confirm` as root
nodes — was rejected for the same three reasons, not on cost.

The equivalent measurements now are in `evals/`: hop count per turn, and the
domain judges over what the turn produced.
