import {
  initialLearningState,
  type LearningState,
  type SubagentTool,
} from "@repo/shared/schemas";
import jsonPatch, { type Operation } from "fast-json-patch";
import { describe, expect, it } from "vitest";

import {
  applyToolResult,
  createStartUpdate,
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

const withMaterial: LearningState = {
  ...initialLearningState,
  stage: "material",
  topic: "Closures",
  research,
  material: {
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

describe("createStartUpdate", () => {
  it.each<[SubagentTool, string]>([
    ["research", "research"],
    ["makeMaterial", "material"],
    ["simplify", "simplify"],
    ["generateQuiz", "quiz"],
    ["evaluate", "evaluate"],
  ])("%s sets status.running to %s", (tool, running) => {
    const { state, patch } = createStartUpdate(initialLearningState, tool);
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
      withMaterial,
      { topic: "Closures", research },
      {
        stage: "research",
        topic: "Closures",
        research,
        material: null,
        quiz: null,
      },
    ],
    [
      "makeMaterial writes the original learning material, clears the quiz",
      "makeMaterial",
      withMaterial,
      { markdown: "# New notes" },
      {
        stage: "material",
        material: {
          original: "# New notes",
          simplified: null,
          view: "original",
        },
        quiz: null,
      },
    ],
    [
      "simplify all writes the simplified view",
      "simplify",
      withMaterial,
      { scope: "all", markdown: "Easy notes" },
      {
        stage: "material",
        material: {
          original: "Closures capture bindings in lexical scope.",
          simplified: "Easy notes",
          view: "simplified",
        },
      },
    ],
    [
      "simplify selection rewrites the selection in the active view",
      "simplify",
      withMaterial,
      {
        scope: "selection",
        selection: "in lexical scope",
        markdown: "where they were made",
      },
      {
        material: {
          original: "Closures capture bindings where they were made.",
          simplified: null,
          view: "original",
        },
      },
    ],
    [
      "generateQuiz writes the quiz",
      "generateQuiz",
      { ...withMaterial, quiz: null },
      { quiz },
      { stage: "quiz", quiz },
    ],
    [
      "evaluate writes the results, the graded answers and marks the quiz submitted",
      "evaluate",
      { ...withMaterial, stage: "quiz" },
      {
        answers: { a: 1 },
        evaluation,
        score: { percent: 100, tier: "Master" },
        feedback: { a2uiOperations: [], summary: "Well done." },
      },
      {
        stage: "evaluation",
        evaluation,
        score: { percent: 100, tier: "Master" },
        quiz: { ...quiz, answers: { a: 1 }, submitted: true },
      },
    ],
  ])("%s", (_, tool, before, data, expected) => {
    const running = createStartUpdate(before, tool).state;
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
    const running = createStartUpdate(withMaterial, "research").state;
    const { state, patch } = applyToolResult(running, "research", content);
    const status = { running: null, error, failed: "research" };

    expect(state).toEqual({ ...withMaterial, status });
    expect(patch).toEqual([{ op: "add", path: "/status", value: status }]);
  });

  it("fails simplify when the selection is gone", () => {
    const { state } = applyToolResult(
      withMaterial,
      "simplify",
      serializeSuccess({
        scope: "selection",
        selection: "missing",
        markdown: "x",
      }),
    );
    expect(state.status).toEqual({
      running: null,
      error: "The selected text is no longer in the learning material.",
      failed: "simplify",
    });
    expect(state.material).toEqual(withMaterial.material);
  });

  it("flags the quiz as outdated when simplify clears it", () => {
    const { state } = applyToolResult(
      withMaterial,
      "simplify",
      serializeSuccess({ scope: "all", markdown: "Simple notes." }),
    );
    expect(state.quiz).toBeNull();
    expect(state.quizOutdated).toBe(true);
  });

  it("does not flag the quiz when simplify had none to clear", () => {
    const { state } = applyToolResult(
      { ...withMaterial, quiz: null },
      "simplify",
      serializeSuccess({ scope: "all", markdown: "Simple notes." }),
    );
    expect(state.quizOutdated).toBe(false);
  });

  it("clears the outdated flag when a new quiz arrives", () => {
    const { state } = applyToolResult(
      { ...withMaterial, quiz: null, quizOutdated: true },
      "generateQuiz",
      serializeSuccess({ quiz }),
    );
    expect(state.quizOutdated).toBe(false);
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
    const running = createStartUpdate(
      initialLearningState,
      "generateQuiz",
    ).state;
    expect(interruptTask(running)?.state.status).toEqual({
      running: null,
      error: "The quiz step did not finish.",
      failed: "quiz",
    });
  });
});
