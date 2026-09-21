import {
  initialLearningState,
  type LearningState,
  type SubagentTool,
} from "@repo/shared/schemas";
import jsonPatch, { type Operation } from "fast-json-patch";
import { describe, expect, it } from "vitest";

import {
  applyToolResult,
  handleStartTask,
  interruptTask,
  isSubagentTool,
} from "@/features/agent/services/state-deltas";

const research = {
  title: "Closures",
  summary: "Functions that remember their scope.",
  keyInsight: "A closure captures bindings, not values.",
  keyTerms: [],
  sources: [],
};

const quiz = {
  id: "q1",
  questions: [
    {
      id: "a",
      concept: "Closures",
      question: "What does a closure capture?",
      options: ["Values", "Bindings", "Types", "Nothing"],
    },
  ],
  answers: {},
  answerKeySealed: "sealed",
  submitted: false,
};

const evaluation = {
  correct: 1,
  total: 1,
  percent: 100,
  weakestConcept: null,
  perQuestion: [
    { qid: "a", correctIndex: 1, isCorrect: true, explanation: "Bindings." },
  ],
  mastery: [{ concept: "Closures", percent: 100 }],
};

const withNotes: LearningState = {
  ...initialLearningState,
  stage: "notes",
  topic: "Closures",
  research,
  notes: {
    original: "Closures capture bindings in lexical scope.",
    simplified: null,
    view: "original",
  },
  quiz,
};

const serializeSuccess = (data: unknown) => JSON.stringify({ ok: true, data });

/** Applies the patch like the AG-UI client does, and checks it. */
const applyPatch = (state: unknown, patch: Operation[]) =>
  jsonPatch.applyPatch(structuredClone(state), patch, true, false).newDocument;

describe("isSubagentTool", () => {
  it("accepts subagent tools only", () => {
    expect(isSubagentTool("research")).toBe(true);
    expect(isSubagentTool("AGUISendStateDelta")).toBe(false);
  });
});

describe("handleStartTask", () => {
  it.each<[SubagentTool, string]>([
    ["research", "research"],
    ["makeNotes", "notes"],
    ["simplify", "simplify"],
    ["generateQuiz", "quiz"],
    ["evaluate", "evaluate"],
  ])("%s sets status.running to %s", (tool, running) => {
    const { state, patch } = handleStartTask(initialLearningState, tool);
    expect(state.status).toEqual({ running });
    expect(patch).toEqual([{ op: "add", path: "/status", value: { running } }]);
  });
});

describe("applyToolResult", () => {
  it.each<
    [string, SubagentTool, LearningState, unknown, Partial<LearningState>]
  >([
    [
      "research writes topic and research, clears later stages",
      "research",
      withNotes,
      { topic: "Closures", research },
      {
        stage: "research",
        topic: "Closures",
        research,
        notes: null,
        quiz: null,
      },
    ],
    [
      "makeNotes writes the original notes, clears the quiz",
      "makeNotes",
      withNotes,
      { markdown: "# New notes" },
      {
        stage: "notes",
        notes: { original: "# New notes", simplified: null, view: "original" },
        quiz: null,
      },
    ],
    [
      "simplify all writes the simplified view",
      "simplify",
      withNotes,
      { scope: "all", markdown: "Easy notes" },
      {
        stage: "notes",
        notes: {
          original: "Closures capture bindings in lexical scope.",
          simplified: "Easy notes",
          view: "simplified",
        },
      },
    ],
    [
      "simplify selection rewrites the selection in the active view",
      "simplify",
      withNotes,
      {
        scope: "selection",
        selection: "in lexical scope",
        markdown: "where they were made",
      },
      {
        notes: {
          original: "Closures capture bindings where they were made.",
          simplified: null,
          view: "original",
        },
      },
    ],
    [
      "generateQuiz writes the quiz",
      "generateQuiz",
      { ...withNotes, quiz: null },
      { quiz },
      { stage: "quiz", quiz },
    ],
    [
      "evaluate writes the results and marks the quiz submitted",
      "evaluate",
      { ...withNotes, stage: "quiz" },
      {
        evaluation,
        score: { percent: 100, tier: "Master" },
        feedback: { a2uiOperations: [], summary: "Well done." },
      },
      {
        stage: "evaluation",
        evaluation,
        score: { percent: 100, tier: "Master" },
        quiz: { ...quiz, submitted: true },
      },
    ],
  ])("%s", (_, tool, before, data, expected) => {
    const running = handleStartTask(before, tool).state;
    const { state, patch } = applyToolResult(
      running,
      tool,
      serializeSuccess(data),
    );

    expect(state).toMatchObject({ ...expected, status: { running: null } });
    expect(applyPatch(running, patch)).toEqual(state);
  });

  it.each<[string, string, string]>([
    [
      "a tool failure",
      JSON.stringify({ ok: false, error: "Search failed." }),
      "Search failed.",
    ],
    [
      "unreadable JSON",
      "not json",
      "The research step returned an unreadable result.",
    ],
    [
      "an invalid result",
      serializeSuccess({ topic: "" }),
      "The research step returned an invalid result.",
    ],
  ])("sets status.error for %s and keeps the data", (_, content, error) => {
    const running = handleStartTask(withNotes, "research").state;
    const { state, patch } = applyToolResult(running, "research", content);

    expect(state).toEqual({ ...withNotes, status: { running: null, error } });
    expect(patch).toEqual([
      { op: "add", path: "/status", value: { running: null, error } },
    ]);
  });

  it("fails simplify when the selection is gone", () => {
    const { state } = applyToolResult(
      withNotes,
      "simplify",
      serializeSuccess({
        scope: "selection",
        selection: "missing",
        markdown: "x",
      }),
    );
    expect(state.status.error).toBe(
      "The selected text is no longer in the notes.",
    );
    expect(state.notes).toEqual(withNotes.notes);
  });

  it("produces a patch that applies to an empty client state", () => {
    const { patch } = applyToolResult(
      initialLearningState,
      "research",
      serializeSuccess({ topic: "Closures", research }),
    );
    expect(() => applyPatch({}, patch)).not.toThrow();
  });
});

describe("interruptTask", () => {
  it("returns null when nothing is running", () => {
    expect(interruptTask(initialLearningState)).toBeNull();
  });

  it("clears a task left running", () => {
    const running = handleStartTask(initialLearningState, "generateQuiz").state;
    expect(interruptTask(running)?.state.status).toEqual({
      running: null,
      error: "The quiz step did not finish.",
    });
  });
});
