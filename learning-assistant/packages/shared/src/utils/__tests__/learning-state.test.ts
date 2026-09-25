import { describe, expect, it } from "vitest";

import { initialLearningState, type LearningState } from "../../schemas";
import { hasTopicWork, readLearningState } from "../learning-state";

describe("readLearningState", () => {
  it("returns the initial state for empty input", () => {
    expect(readLearningState(undefined)).toEqual(initialLearningState);
    expect(readLearningState({})).toEqual(initialLearningState);
  });

  it("fills missing keys from the initial state", () => {
    expect(readLearningState({ topic: "Closures" })).toEqual({
      ...initialLearningState,
      topic: "Closures",
    });
  });

  it("returns the initial state for invalid input", () => {
    expect(readLearningState({ stage: "done" })).toEqual(initialLearningState);
  });
});

describe("hasTopicWork", () => {
  const withMaterial: LearningState = {
    ...initialLearningState,
    topic: "Closures",
    material: { original: "# Notes", simplified: null, view: "original" },
  };

  it("is false with only research or nothing", () => {
    expect(hasTopicWork(initialLearningState)).toBe(false);
    expect(hasTopicWork({ ...initialLearningState, topic: "Closures" })).toBe(
      false,
    );
  });

  it("is true once learning material or a quiz exists", () => {
    expect(hasTopicWork(withMaterial)).toBe(true);
    expect(
      hasTopicWork({
        ...initialLearningState,
        score: { percent: 80, tier: "Master" },
      }),
    ).toBe(true);
  });
});
