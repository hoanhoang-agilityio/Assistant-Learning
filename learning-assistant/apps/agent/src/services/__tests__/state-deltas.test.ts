import { MAX_BOARD_SURFACES } from "@repo/shared/a2ui/board-catalog";
import {
  type BoardSurface,
  initialLearningState,
  type LearningState,
  type SubagentTool,
} from "@repo/shared/schemas";
import jsonPatch, { type Operation } from "fast-json-patch";
import { describe, expect, it } from "vitest";

import {
  applyBoardDraft,
  applyDraft,
  applyRemovalResult,
  applySurfaceResult,
  applyToolResult,
  createStartUpdate,
  interruptTask,
  isSubagentTool,
} from "../state-deltas";

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

describe("applyDraft", () => {
  it("writes the running task's draft", () => {
    const running = createStartUpdate(initialLearningState, "makeMaterial");
    const draft = { task: "material" as const, markdown: "# Clo" };
    const update = applyDraft(running.state, draft);

    expect(update?.patch).toEqual([
      { op: "add", path: "/draft", value: draft },
    ]);
  });

  it("ignores a draft for a task that is not running", () => {
    expect(
      applyDraft(initialLearningState, { task: "material", markdown: "x" }),
    ).toBeNull();
  });

  it("is cleared by the task's result", () => {
    const running = createStartUpdate(withMaterial, "makeMaterial").state;
    const drafted = applyDraft(running, { task: "material", markdown: "# C" });
    const done = applyToolResult(
      drafted?.state ?? running,
      "makeMaterial",
      serializeSuccess({ markdown: "# Closures" }),
    );

    expect(done.state.draft).toBeNull();
  });
});

const ROOT = { id: "root", component: "Stack", children: ["p1", "p2"] };
const PARAGRAPH = { id: "p1", component: "Paragraph", text: "Hello" };

describe("applyBoardDraft", () => {
  const renderCall = (args: unknown) => ({
    toolCallId: "c1",
    toolCallName: "renderSurface",
    args,
  });

  it("drafts a new canvas view from the components written so far", () => {
    const update = applyBoardDraft(
      initialLearningState,
      renderCall({
        target: "canvas",
        title: "Overview",
        components: [ROOT, PARAGRAPH, { id: "p2", component: "Parag" }],
      }),
    );

    expect(update?.state.boardDraft).toMatchObject({
      id: "board-draft-c1",
      title: "Overview",
    });
    expect(update?.state.boardDraft?.operations[1]).toMatchObject({
      updateComponents: {
        surfaceId: "board-draft-c1",
        components: [{ ...ROOT, children: ["p1"] }, PARAGRAPH],
      },
    });
  });

  it("waits for the target, the title and the root", () => {
    for (const args of [
      { target: "chat", title: "Card", components: [ROOT] },
      { target: "canvas", title: "", components: [ROOT] },
      { target: "canvas", title: "Overview", components: [PARAGRAPH] },
      "not an object",
    ]) {
      expect(
        applyBoardDraft(initialLearningState, renderCall(args)),
      ).toBeNull();
    }
  });

  it("drafts a revision under the id of the view it revises", () => {
    const state = {
      ...initialLearningState,
      board: [createSurface("board-1")],
    };
    const call = (surfaceId: string) => ({
      toolCallId: "c2",
      toolCallName: "updateBoardSurface",
      args: { surfaceId, title: "Revised", components: [ROOT] },
    });

    expect(applyBoardDraft(state, call("board-1"))?.state.boardDraft?.id).toBe(
      "board-1",
    );
    expect(applyBoardDraft(state, call("board-"))).toBeNull();
  });
});

describe("interruptTask", () => {
  it("returns null when nothing is running", () => {
    expect(interruptTask(initialLearningState)).toBeNull();
  });

  it("clears a Board view left half-written", () => {
    const state = {
      ...initialLearningState,
      boardDraft: { id: "board-draft-c1", title: "Overview", operations: [] },
    };
    expect(interruptTask(state)?.patch).toEqual([
      { op: "add", path: "/boardDraft", value: null },
    ]);
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

const createSurface = (id: string): BoardSurface => ({
  id,
  title: `View ${id}`,
  operations: [{ version: "v0.9", createSurface: { surfaceId: id } }],
  revision: 1,
});

describe("applySurfaceResult", () => {
  it("adds a canvas view to the Board and patches only the board", () => {
    const surface = createSurface("board-1");
    const update = applySurfaceResult(
      initialLearningState,
      JSON.stringify({ surface }),
    );

    expect(update?.state.board).toEqual([surface]);
    expect(update?.patch).toEqual([
      { op: "add", path: "/board", value: [surface] },
    ]);
  });

  it("replaces a view with the same id and keeps the newest last", () => {
    const state = {
      ...initialLearningState,
      board: [createSurface("a"), createSurface("b")],
    };
    const revised = { ...createSurface("a"), title: "Revised", revision: 2 };
    const update = applySurfaceResult(
      state,
      JSON.stringify({ surface: revised }),
    );

    expect(update?.state.board.map(({ id }) => id)).toEqual(["b", "a"]);
    expect(update?.state.board[1]).toMatchObject({
      title: "Revised",
      revision: 2,
    });
  });

  it("drops the oldest views past the limit", () => {
    const state = {
      ...initialLearningState,
      board: Array.from({ length: MAX_BOARD_SURFACES }, (_, index) =>
        createSurface(`s${index}`),
      ),
    };
    const update = applySurfaceResult(
      state,
      JSON.stringify({ surface: createSurface("new") }),
    );

    expect(update?.state.board).toHaveLength(MAX_BOARD_SURFACES);
    expect(update?.state.board[0]?.id).toBe("s1");
    expect(update?.state.board.at(-1)?.id).toBe("new");
  });

  it("clears the Board draft, even when the result is an error", () => {
    const state = {
      ...initialLearningState,
      boardDraft: { id: "board-draft-c1", title: "Overview", operations: [] },
    };
    const surface = createSurface("board-1");

    expect(
      applySurfaceResult(state, JSON.stringify({ surface }))?.state,
    ).toMatchObject({ board: [surface], boardDraft: null });
    expect(
      applySurfaceResult(state, JSON.stringify({ error: "bad tree" }))?.patch,
    ).toEqual([{ op: "add", path: "/boardDraft", value: null }]);
  });

  it("ignores chat results, errors and unreadable content", () => {
    for (const content of [
      JSON.stringify({ a2ui_operations: [] }),
      JSON.stringify({ error: "bad tree" }),
      "not json",
    ]) {
      expect(applySurfaceResult(initialLearningState, content)).toBeNull();
    }
  });
});

describe("applyRemovalResult", () => {
  it("takes the removed views off the Board", () => {
    const state = {
      ...initialLearningState,
      board: [createSurface("a"), createSurface("b"), createSurface("c")],
    };
    const update = applyRemovalResult(
      state,
      JSON.stringify({
        removed: [
          { id: "a", title: "View a" },
          { id: "c", title: "View c" },
        ],
      }),
    );

    expect(update?.state.board.map(({ id }) => id)).toEqual(["b"]);
    expect(update?.patch).toEqual([
      { op: "add", path: "/board", value: update?.state.board },
    ]);
  });

  it("ignores errors, unreadable content and ids already gone", () => {
    const state = { ...initialLearningState, board: [createSurface("a")] };
    for (const content of [
      JSON.stringify({ error: "no such view" }),
      "not json",
      JSON.stringify({ removed: [{ id: "gone", title: "Gone" }] }),
    ]) {
      expect(applyRemovalResult(state, content)).toBeNull();
    }
  });
});
