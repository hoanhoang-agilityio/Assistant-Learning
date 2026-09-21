import { describe, expect, it } from "vitest";

import { getOptionState } from "@/features/canvas/utils/quiz-options";

const wrong = { correctIndex: 2, isCorrect: false, explanation: "" };
const right = { correctIndex: 1, isCorrect: true, explanation: "" };

describe("getOptionState", () => {
  it("marks only the choice before grading", () => {
    expect(getOptionState(1, 1, null)).toBe("selected");
    expect(getOptionState(0, 1, null)).toBe("idle");
    expect(getOptionState(0, null, null)).toBe("idle");
  });

  it("shows the correct option and a wrong choice after grading", () => {
    expect(getOptionState(2, 1, wrong)).toBe("correct");
    expect(getOptionState(1, 1, wrong)).toBe("incorrect");
    expect(getOptionState(0, 1, wrong)).toBe("idle");
  });

  it("shows a right choice as correct", () => {
    expect(getOptionState(1, 1, right)).toBe("correct");
  });
});
