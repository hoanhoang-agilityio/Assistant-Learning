# Manual test results

End-to-end run of every user flow in the browser, against the real model.

- **Date:** 2026-09-25
- **Code under test:** `learning-assistant` at `881ac60`, plus two uncommitted fixes made during the run (see [Fixes made](#fixes-made)). The branches `feat/agent-event-log`, `chore/runtime-debug-flag`, `perf/draft-state-diff`, `fix/chat-history-on-mode-switch`, `fix/stepper-line-alignment` and `docs/m8-board-streaming` were not merged, so their changes were not part of this run.
- **Model:** `gpt-5.4-mini`, the user's own key. `TAVILY_API_KEY` set.
- **Settings:** beginner level; question count changed to 4 during the run.
- **How it was checked:** each message was sent in the app's chat (or the canvas button was pressed), and the AG-UI stream of `/api/copilotkit/agent/learning/run` was read in the page. The tables list the tools the Supervisor called and the state keys that changed.

## Summary

| Result                         | Count  |
| ------------------------------ | ------ |
| Pass                           | 23     |
| Pass after a fix in this run   | 1      |
| Partial (works, wrong message) | 1      |
| Intermittent fail              | 1      |
| **Total**                      | **26** |

## Cases

| #   | Flow                       | Input                                                                 | Expected                                                 | Observed                                                                                                                                                                   | Result                     |
| --- | -------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| 1   | Missing prerequisite       | "make a quiz for me" (empty canvas)                                   | Explain that material is needed; no tool                 | Text reply: needs learning material first, offers to research                                                                                                              | Pass                       |
| 2   | Chat card: concept         | "What is a closure in JavaScript?"                                    | `showConceptCard`, no research                           | `showConceptCard`                                                                                                                                                          | Pass                       |
| 3   | Chat card: comparison      | "let vs const in JavaScript, what is the difference?"                 | `showComparison`                                         | `showComparison`, table rendered                                                                                                                                           | Pass                       |
| 4   | Chat card: steps           | "How does the JavaScript event loop work?"                            | `showSteps`                                              | `showSteps`                                                                                                                                                                | Pass                       |
| 5   | Chat card: code            | "Show me a code example of a closure counter in JavaScript"           | `showCodeExample`                                        | `showCodeExample`                                                                                                                                                          | Pass                       |
| 6   | Chat panel (A2UI)          | "Give me a small panel in the chat about JavaScript primitive types…" | `renderSurface` target chat, Board untouched             | `renderSurface` → `ACTIVITY_SNAPSHOT a2ui-surface`; Board empty                                                                                                            | Pass                       |
| 7   | Research                   | "Research JavaScript closures"                                        | `research` only                                          | `research`; `stage`, `topic`, `research` set                                                                                                                               | Pass                       |
| 8   | Learning material          | "Make learning material"                                              | `makeMaterial`                                           | `makeMaterial`; `stage`, `material` set                                                                                                                                    | Pass                       |
| 9   | Simplify all               | "Simplify the learning material…", then **Simplify all** button       | `simplify(scope "all")`, Simplified view                 | Failed twice: the model sent `selection: ""`, the schema rejected it. After the fix: success, Simplified view set                                                          | Pass after fix             |
| 10  | Simplify selection         | **Edit**, select a sentence, **Simplify selection**                   | `simplify(scope "selection")` with the exact text        | Exact text passed; material updated                                                                                                                                        | Pass                       |
| 11  | Settings from chat         | "Please use 4 questions for my quizzes"                               | `setLearningSettings(questionCount 4)`, next run sends 4 | Store and the next run's `forwardedProps.settings` both 4. The model also sent the unchanged `learningLevel`                                                               | Pass (minor, see note)     |
| 12  | Quiz honours the count     | Quiz after case 11                                                    | 4 questions                                              | 4 questions                                                                                                                                                                | Pass                       |
| 13  | Autopilot                  | "Teach me JavaScript closures end to end"                             | `research` → `makeMaterial` → `generateQuiz`, then stop  | All three in one run (20 s), stopped, no `evaluate`                                                                                                                        | Pass                       |
| 14  | Submit button grading      | Answer 4 questions (1 wrong), **Submit**                              | Graded in code, 3/4, 75 %, Practitioner, no chat reply   | `evaluate` at +3 ms (before any LLM step); 75 % Practitioner; Evaluation, Score, Feedback set                                                                              | Pass                       |
| 15  | Reflection                 | Rating 4, note, **Save reflection & send to chat**                    | Text reply, no tool                                      | Text reply; `reflection` set                                                                                                                                               | Pass                       |
| 16  | New questions              | "Give me new questions"                                               | New quiz; old results cleared                            | `generateQuiz`; evaluation, score, feedback, reflection cleared                                                                                                            | Pass                       |
| 17  | Grade from chat            | Answer all, "please grade my answers"                                 | Supervisor calls `evaluate`                              | `evaluate`; 3/4                                                                                                                                                            | Pass                       |
| 18  | Board: create              | "Put a cheat sheet of common closure patterns on the board"           | `renderSurface` target canvas; one Board view            | First call rejected (`unresolved_child`), model fixed it and the second call drew the view                                                                                 | Pass                       |
| 19  | Board: edit                | "Add a tip about memory leaks to the cheat sheet"                     | `readBoardSurface` → `updateBoardSurface`, same id       | Same id, revision 1 → 2, tip present                                                                                                                                       | Pass                       |
| 20  | Board: delete              | "Delete the cheat sheet from the board"                               | `deleteBoardSurface`; Board empty                        | Board empty                                                                                                                                                                | Pass                       |
| 21  | Theme                      | "Switch to light mode", then "Go back to my device theme"             | `setTheme` light, then system                            | Both applied and saved                                                                                                                                                     | Pass                       |
| 22  | Layout / device preview    | "Show me the tablet layout", then "Go back to the automatic view"     | `setLayout(view)`                                        | Both applied. The model also sent the unchanged `chat: "docked"`                                                                                                           | Pass (minor, see note)     |
| 23  | New topic, no confirmation | "Research black holes" with material and a graded quiz                | `confirmNewTopic` card                                   | **Once:** `research` called directly; material, quiz and results wiped with no card. **Three later tries** (same kind of state, incl. an exact rebuild): the card appeared | Intermittent fail (1 of 4) |
| 24  | New topic: keep            | "Research volcanoes" → **Keep current topic**                         | No research; topic unchanged                             | Card shown; after Keep no tool ran; topic stayed                                                                                                                           | Pass                       |
| 25  | New topic: confirm         | "Actually, research volcanoes" → **Start new topic**                  | Canvas cleared, then `research("volcanoes")`             | Cleared, researched volcanoes                                                                                                                                              | Pass                       |
| 26  | Stop                       | "Give me new questions", then **Stop** on the card                    | Run stops; old quiz kept; "stopped" message              | Run stopped, old quiz kept. The stage shows "This tool call failed before it returned a result (invalid arguments…)" with Retry                                            | Partial                    |

Two earlier checks from the same day, after the Board prompt fix:

| #   | Flow                       | Input                                          | Observed                                                        | Result |
| --- | -------------------------- | ---------------------------------------------- | --------------------------------------------------------------- | ------ |
| 27  | Board request with a topic | "show me all IPA in board"                     | One `renderSurface` view "IPA Cheat Sheet"; stages stayed empty | Pass   |
| 28  | Research only (regression) | "research the International Phonetic Alphabet" | `research` only, no chain into material or quiz                 | Pass   |

## Fixes made

| Problem                                                                | Cause                                                                                                                 | Fix                                                                                                                                                                  |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "show me all IPA in board" ran research, material and a quiz (case 27) | The Board was not in the Supervisor's main tool table, "all X" matched Autopilot, and "board" alone was not a trigger | `apps/agent/src/services/prompts/supervisor.ts`: Board row in the tool table, Board rule, narrower Autopilot, Examples block                                         |
| "Simplify all" always failed (case 9)                                  | The model sends `selection: ""` for scope `all`; `selection` had `.min(1)`, so the AI SDK rejected the call           | `packages/shared/src/schemas/tool-params.ts`: dropped `.min(1)` (the tool already refuses an empty selection for scope `selection`); test added in `schemas.test.ts` |

## Open issues

1. **New topic can skip the confirmation (case 23), losing work.** The model is the only guard: `research` runs whenever it is called. It could not be reproduced on demand, and it is not known whether the tool was not offered on that run or offered and ignored. Suggested fix: make the server refuse `research` while material or a quiz exists (the confirm card clears the state before its follow-up run, so a confirmed switch still works). This needs a "refused, confirm first" result that does not set `status.error`, otherwise the stage shows an error with Retry.
2. **Stopping a step shows a misleading error (case 26).** A stopped tool call has no result, so `closeLostToolCalls` fills in the generic "failed before it returned a result (invalid arguments…)" message and the stage offers Retry. It should read as stopped (`TOOL_ERRORS.stopped`, "The student stopped this step.") without an error state.
3. **Display tools send settings the student did not ask to change (cases 11, 22).** `setLearningSettings` sent the current `learningLevel`, and `setLayout` sent the current `chat`. Harmless while they equal the current value; the tool descriptions already say "send only what the student asked to change".
4. **Simplify all copies the whole material into `selection` (case 9).** With scope `all` the model sometimes pastes the full notes into `selection`, which the tool ignores. Wasted tokens only.

## Not covered

- A wrong or expired OpenAI key, quota errors and a missing `TAVILY_API_KEY`.
- **Retake**, the **Review …** link and editing the notes by hand (`quizOutdated`).
- Hiding and reopening the chat, and the chat-history fix (branch `fix/chat-history-on-mode-switch`, not merged).
- The learning level changing the depth of research, material and quiz.
- Anything after a page reload: state lives in the session only, so a reload starts over.
