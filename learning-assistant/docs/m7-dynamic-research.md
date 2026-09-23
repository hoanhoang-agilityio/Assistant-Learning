# M7 — Dynamic Research surface

2026-09-23 · Hoan Minh Hoang · Builds on [v1-tasks.md](./v1-tasks.md) · Design: [design.md](./design.md)

Today every topic gets the same Research page: article, key insight, flashcards, sources
(`shared/a2ui/templates/research.json`). This milestone lets the surface change with the
topic — a timeline for a history topic, a code example for a programming one — without
giving up the structured data that Notes and the Quiz are built from.

13 tasks, same conventions as v1: `M7.<n>`, S ≤ 2h / M ≤ half a day / L ≤ 1 day,
`web/` = `apps/web/`, `shared/` = `packages/shared/src/`.

## The two decisions this rests on

**1. Content stays data; only the arrangement is dynamic.** The Research agent returns
typed section blocks inside `ResearchResult`, and code turns those blocks into A2UI
components. The model does not author component trees.

The alternative — the model calling `render_a2ui` the way
`subagents/feedback-surface.ts` does — costs a second LLM call, a retry loop and a
failure path, and it buries the content inside component props where
`createNotesPrompt` (`services/prompts/subagents.ts:43`) can no longer read it. Notes
feed the Quiz, so content that only exists as UI is content the student is never
quizzed on.

**2. Layout is separate from content, so re-arranging costs nothing.** `sections` holds
the blocks; `layout` holds their ids in display order, and an id left out is hidden, not
deleted. A request to reorder or hide is an array operation with no model call, and it
never touches `summary`, `keyTerms` or the notes the student has already edited.

That gives three tiers, and the Supervisor picks between them:

| The student asks | Runs | Cost | Downstream |
| --- | --- | --- | --- |
| "reorder these", "hide the sources" | `updateResearchLayout` | none | nothing stale |
| "add a comparison of X and Y", "show this as a timeline" | `addResearchSection` | one small call, no Tavily | notes miss a section |
| "research this again", "find newer sources", a different topic | `research` (existing) | full | notes and quiz cleared |

## Schema

```ts
ResearchResult = {
  title, summary, keyInsight, keyTerms, sources,   // unchanged
  sections: ResearchSection[],                     // default []
  layout: string[],                                // default []; ordered section ids
}

ResearchSection =
  | { id, type: "comparison",     title, columns: string[], rows: { label, values }[] }
  | { id, type: "timeline",       title, events: { when, label, detail }[] }
  | { id, type: "process",        title, steps: { title, detail }[] }
  | { id, type: "code",           title, language, code, caption }
  | { id, type: "misconceptions", title, items: { myth, fact }[] }
```

`sections` and `layout` default to `[]`, so research saved before this milestone still
parses and renders exactly as it does today.

Ids are assigned in code, never by the model: `createSectionId(existing)` returns
`s<max + 1>`. The model returns drafts without ids, which keeps ids unique across
`addResearchSection` calls and stops a model-chosen id from colliding with a live one.

## Components

Added to the `learning-assistant/canvas/v1` catalog: **Section** (heading + children) and
one component per section type — **ComparisonTable**, **Timeline**, **ProcessSteps**,
**CodeExample**, **Misconceptions**. ArticleCard, InsightCallout, Flashcards and
SourceList stay as the fixed backbone of every Research surface.

Deliberately not built:

| Dropped | Why |
| --- | --- |
| Grid | The canvas panel is narrow, so a grid collapses to one column. The basic catalog already has Row/Column |
| Quote | An invented quote attributed to a real person is the worst failure this surface could produce |
| KeyTerms | Same term/definition data as Flashcards; two views of one thing only makes the model waffle between them |
| ConceptMap | Needs a graph layout library, and models lay out graphs badly. Most expensive item, least return |
| QuizPreview | The Quiz stage owns this, and it deliberately keeps the answer key off the client (`__tests__/quiz-security.test.ts`) |

Sources stay bound from the data model and are never model-authored: they come from
Tavily in code (`subagents/research.ts:17`), which is what makes a cited URL always one
that was actually retrieved.

## Tasks

### Schema and rendering

- [ ] **M7.1** (M) `shared/schemas/research.ts`: the `ResearchSection` discriminated union,
      `sections` and `layout` with `.default([])`, a draft union without `id` for the
      model, and `getVisibleSections(research)` returning the sections in `layout` order.
      `createSectionId` in the same file. Extend `schemas.test.ts`: old research parses,
      unknown layout ids are rejected, `getVisibleSections` honours order and omission.
- [ ] **M7.2** (M) `web/features/canvas/components/a2ui/`: `Section/`, `ComparisonTable/`,
      `Timeline/`, `ProcessSteps/`, `Misconceptions/` as `<Name>/index.tsx`, props-only,
      Tailwind matching the existing cards, dark mode included.
- [ ] **M7.3** (S) `a2ui/CodeExample/` + `CodeExampleView/`: monospace block with the
      language shown and a copy button (logic in `use-code-example.ts`). No syntax
      highlighting dependency in this milestone — it is a bundle cost for a small gain.
- [ ] **M7.4** (M) `features/canvas/constants/a2ui-catalog.ts`: zod3 prop schemas for the
      six components and their entries in `CANVAS_COMPONENT_DEFINITIONS` / `CANVAS_CATALOG`.
      Matching item types in `features/canvas/types/a2ui.ts`, and `ResearchDataModel`
      gaining `sections`.
- [ ] **M7.5** (L) `features/canvas/utils/build-surface.ts`: `createResearchSurface(research)`
      returns a `SurfaceTemplate` built from the visible sections — root Stack children are
      `article`, then one `section-<i>` per visible section, then `sources`; each section
      component binds to `/sections/<i>`. `createResearchDataModel` returns the research plus
      the ordered visible sections. Delete `templates/research.json` and `RESEARCH_TEMPLATE`.
      Vitest per section type, plus the empty-`sections` case matching today's output.
- [ ] **M7.6** (S) `features/canvas/hooks/use-canvas-surface.ts`: it currently sends
      `createSurface`/`updateComponents` once, guarded on `getSurface`, so a changed
      component list never reaches the renderer. Split it: create once, then send
      `updateComponents` whenever `template.components` changes. The fixed surfaces keep
      their current behaviour because their components are referentially stable.
- [ ] **M7.7** (S) `stages/ResearchStage/` + `hooks/use-research-stage.ts`: memoise the
      generated template and the data model on `research`, so one state update produces one
      component update and one data-model update.

### Agent

- [ ] **M7.8** (M) `subagents/research.ts` + `prompts/subagents.ts`: the draft schema gains
      `sections` (draft form, no ids); code assigns ids and the initial `layout`. The system
      prompt says when each type applies, caps it at 0–4 sections, forbids two sections of
      the same type unless their focus differs, and keeps sections out for a topic that
      suits plain prose.
- [ ] **M7.9** (M) `subagents/research-section.ts` + its prompts: existing research plus a
      requested type and optional focus → one section draft. It reads the research already
      in state and never searches, so `title`, `summary`, `keyInsight` and the student's
      notes are untouched. Register `addResearchSection` in `tools/learning-tools.ts` with
      its `ToolParamSchemas` / `ToolResultSchemas` entries; the applier appends to
      `sections` and `layout`. `SUBAGENT_CLEARS.addResearchSection` is `[]` — adding a
      section must not clear the quiz.
- [ ] **M7.10** (M) `updateResearchLayout({ order })`: no model call. `order` is the new
      visible order; an id left out is hidden. Unknown ids fail with a new
      `TOOL_ERRORS.unknownSection` the Supervisor can explain. This needs
      `SUBAGENT_TASK` to allow `null` (`Record<SubagentTool, RunningTask | null>`) so
      `createStartUpdate` skips the running flag and the canvas does not flash a
      skeleton on a reorder; `createFailureUpdate` then takes a nullable task and leaves
      `status.failed` unset. Extend `state-deltas.test.ts` for both tools.
- [ ] **M7.11** (S) `services/supervisor-state.ts`: `research` gains
      `sections: { id, type, title }[]` and the visible order, so the model can name real
      ids in `updateResearchLayout` instead of guessing them.
- [ ] **M7.12** (S) `prompts/supervisor.ts`: the three tiers in `TOOL_ROUTING`, with
      re-research as the option that needs an explicit reason — the topic changed, or the
      student asked for fresh sources. Ambiguous phrasing ("make this a comparison table")
      resolves to the cheap tier, since that one is reversible.
- [ ] **M7.13** (S) Notes coverage: `createNotesPrompt` renders `sections` as text so the
      notes — and therefore the quiz — cover them. Add `notesOutdated` to `LearningState`,
      set by `addResearchSection` (never by a layout change), shown with the existing
      `QuizOutdatedBanner` pattern so the Supervisor can offer to update the notes rather
      than silently rewriting notes the student edited by hand.

## Order and dependencies

M7.1 first — everything else types against it. M7.2–M7.7 (rendering) and M7.8–M7.13
(agent) can then go in parallel; M7.5 depends on M7.4, and M7.10 must land before M7.12
so the prompt describes tools that exist. Suggested PRs: **M7.1**, **M7.2 + M7.3**,
**M7.4 + M7.5 + M7.6 + M7.7**, **M7.8**, **M7.9 + M7.13**, **M7.10 + M7.11 + M7.12**.

## Risks

- **The model over-sections.** Every topic gets four blocks and the page turns into a
  gallery. The caps and the "plain prose is fine" line in M7.8 are the defence; check it
  on three or four unlike topics before calling M7.8 done.
- **The Supervisor picks re-research for a layout request.** That is the only destructive
  tier, so M7.12's wording matters more than the other prompt changes.
- **Generated components churn.** If `createResearchSurface` returns a new array on every
  render, M7.6 turns that into an `updateComponents` per render. M7.7's memoisation is
  what keeps it to one per state change.

## Definition of done

`pnpm lint`, `pnpm check-types` and `pnpm test` pass. In the browser: research a history
topic and a programming topic and see different surfaces; ask to reorder and to hide a
section and see it happen with no model call and no notes change; ask for a section type
that is not there and see it appended with the reading intact; ask to research again and
see the full reset. Conventional commit per PR.
