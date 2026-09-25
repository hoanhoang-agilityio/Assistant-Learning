import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { toSupervisorState } from "../supervisor-state";

describe("toSupervisorState", () => {
  it("keeps short summaries and drops the full learning material, quiz and Board views", () => {
    const state: LearningState = {
      ...initialLearningState,
      stage: "quiz",
      topic: "Closures",
      material: {
        original: "# Closures\nLong notes",
        simplified: null,
        view: "original",
      },
      quiz: {
        id: "q1",
        questions: [
          {
            id: "a",
            concept: "Closures",
            question: "What does a closure capture?",
            options: ["Values", "Bindings", "Types", "Nothing"],
          },
        ],
        answers: { a: 1 },
        answerKeySealed: "sealed",
        submitted: false,
      },
      board: [
        {
          id: "board-1",
          title: "HTTP methods",
          operations: [{ version: "v0.9", createSurface: { surfaceId: "x" } }],
          revision: 1,
        },
      ],
    };

    const trimmed = toSupervisorState(state, DEFAULT_SETTINGS);

    expect(trimmed).toEqual({
      settings: {
        questionCount: DEFAULT_SETTINGS.questionCount,
        learningLevel: DEFAULT_SETTINGS.learningLevel,
      },
      stage: "quiz",
      status: { running: null },
      topic: "Closures",
      research: null,
      material: { view: "original", hasSimplified: false, characters: 21 },
      quiz: { questionCount: 1, answeredCount: 1, submitted: false },
      evaluation: null,
      score: null,
      hasFeedback: false,
      hasReflection: false,
      quizOutdated: false,
      board: [{ id: "board-1", title: "HTTP methods" }],
    });
    expect(JSON.stringify(trimmed)).not.toContain("Bindings");
    expect(JSON.stringify(trimmed)).not.toContain("createSurface");
    expect(JSON.stringify(trimmed)).not.toContain("sealed");
  });
});
