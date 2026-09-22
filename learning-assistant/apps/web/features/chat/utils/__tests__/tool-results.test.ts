import { describe, expect, it } from "vitest";

import {
  formatQuizSize,
  formatToolTitle,
  getToolPhase,
  parseEvaluateScore,
  parseToolError,
} from "@/features/chat/utils/tool-results";

describe("parseToolError", () => {
  it("returns the error of a failed result", () => {
    expect(parseToolError('{"ok":false,"error":"No notes yet."}')).toBe(
      "No notes yet.",
    );
  });

  it.each([undefined, "", '{"ok":true,"data":{}}', "plain text"])(
    "returns null for %j",
    (result) => {
      expect(parseToolError(result)).toBeNull();
    },
  );
});

describe("getToolPhase", () => {
  it.each([
    ["inProgress", true, null, "running"],
    ["executing", true, null, "running"],
    ["executing", false, null, "stopped"],
    ["complete", false, null, "done"],
    ["complete", true, "Search failed.", "failed"],
  ] as const)(
    "%s, running %s, error %j → %s",
    (status, isRunning, error, phase) => {
      expect(getToolPhase(status, isRunning, error)).toBe(phase);
    },
  );
});

describe("formatToolTitle", () => {
  it("adds the detail while running and when done", () => {
    expect(formatToolTitle("research", "running", "Closures")).toBe(
      "Researching “Closures”…",
    );
    expect(formatToolTitle("research", "done", "Closures")).toBe(
      "Research ready: Closures",
    );
  });

  it("uses the plain label without a detail, and when failed or stopped", () => {
    expect(formatToolTitle("makeNotes", "running")).toBe("Writing notes…");
    expect(formatToolTitle("makeNotes", "done")).toBe("Notes ready");
    expect(formatToolTitle("research", "failed", "Closures")).toBe(
      "Research failed",
    );
    expect(formatToolTitle("research", "stopped", "Closures")).toBe(
      "Research stopped",
    );
  });
});

describe("formatQuizSize", () => {
  const question = {
    id: "q1",
    concept: "A",
    question: "One?",
    options: ["a", "b", "c", "d"],
  };
  const quiz = {
    id: "quiz-1",
    questions: [question, { ...question, id: "q2" }],
    answers: {},
    answerKeySealed: "sealed",
    submitted: false,
  };

  it("counts the questions in a successful result", () => {
    expect(formatQuizSize(JSON.stringify({ ok: true, data: { quiz } }))).toBe(
      "2 questions",
    );
  });

  it.each([undefined, "not json", JSON.stringify({ ok: false, error: "x" })])(
    "is undefined for %j",
    (result) => {
      expect(formatQuizSize(result)).toBeUndefined();
    },
  );
});

describe("parseEvaluateScore", () => {
  const data = {
    answers: { q1: 0 },
    evaluation: {
      correct: 1,
      total: 1,
      percent: 100,
      weakestConcept: null,
      perQuestion: [
        { qid: "q1", correctIndex: 0, isCorrect: true, explanation: "" },
      ],
      mastery: [{ concept: "A", percent: 100 }],
    },
    score: { percent: 100, tier: "Master" },
    feedback: { a2uiOperations: [], summary: "Great." },
  };

  it("reads the score from a successful result", () => {
    expect(parseEvaluateScore(JSON.stringify({ ok: true, data }))).toEqual({
      percent: 100,
      tier: "Master",
    });
  });

  it.each([
    undefined,
    "not json",
    JSON.stringify({ ok: false, error: "No quiz" }),
  ])("is null for %s", (result) => {
    expect(parseEvaluateScore(result)).toBeNull();
  });
});
