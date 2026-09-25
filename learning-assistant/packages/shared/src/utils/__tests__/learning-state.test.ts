import { describe, expect, it } from "vitest";

import { initialLearningState } from "../../schemas";
import { readLearningState } from "../learning-state";

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
