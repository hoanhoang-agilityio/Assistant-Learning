import { describe, expect, it } from "vitest";

import {
  formatQuizSize,
  formatToolTitle,
  getToolPhase,
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
