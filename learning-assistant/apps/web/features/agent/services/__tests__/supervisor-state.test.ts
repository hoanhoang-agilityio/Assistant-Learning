import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { toSupervisorState } from "@/features/agent/services/supervisor-state";

describe("toSupervisorState", () => {
  it("keeps short summaries and drops the full notes and quiz", () => {
    const state: LearningState = {
      ...initialLearningState,
      stage: "quiz",
      topic: "Closures",
      notes: {
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
    };

    const trimmed = toSupervisorState(state);

    expect(trimmed).toEqual({
      stage: "quiz",
      status: { running: null },
      topic: "Closures",
      research: null,
      notes: { view: "original", hasSimplified: false, characters: 21 },
      quiz: { questionCount: 1, answeredCount: 1, submitted: false },
      score: null,
      hasFeedback: false,
      hasReflection: false,
    });
    expect(JSON.stringify(trimmed)).not.toContain("Bindings");
    expect(JSON.stringify(trimmed)).not.toContain("sealed");
  });
});
