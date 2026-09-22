import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  createNewTopicDecision,
  hasTopicWork,
  parseNewTopicDecision,
  resetForNewTopic,
} from "@/features/chat/utils/new-topic";

const withNotes: LearningState = {
  ...initialLearningState,
  topic: "Closures",
  notes: { original: "# Notes", simplified: null, view: "original" },
};

describe("hasTopicWork", () => {
  it("is false with only research or nothing", () => {
    expect(hasTopicWork(initialLearningState)).toBe(false);
    expect(hasTopicWork({ ...initialLearningState, topic: "Closures" })).toBe(
      false,
    );
  });

  it("is true once notes or a quiz exist", () => {
    expect(hasTopicWork(withNotes)).toBe(true);
    expect(
      hasTopicWork({
        ...initialLearningState,
        score: { percent: 80, tier: "Master" },
      }),
    ).toBe(true);
  });
});

describe("resetForNewTopic", () => {
  it("clears every stage", () => {
    expect(resetForNewTopic()).toEqual(initialLearningState);
  });
});

describe("createNewTopicDecision", () => {
  it("tells the Supervisor to research the new topic on confirm", () => {
    const decision = createNewTopicDecision(true, "Rust", "Closures");
    expect(decision.confirmed).toBe(true);
    expect(decision.instruction).toContain('research with topic "Rust"');
  });

  it("tells the Supervisor to stay on the current topic on keep", () => {
    const decision = createNewTopicDecision(false, "Rust", "Closures");
    expect(decision.confirmed).toBe(false);
    expect(decision.instruction).toContain('"Closures"');
    expect(decision.instruction).toContain("Do not call research");
  });

  it("round-trips through the tool result", () => {
    const decision = createNewTopicDecision(false, "Rust", null);
    expect(parseNewTopicDecision(JSON.stringify(decision))).toEqual(decision);
  });
});

describe("parseNewTopicDecision", () => {
  it.each([undefined, "", "not json", '{"confirmed":"yes"}'])(
    "returns null for %j",
    (result) => {
      expect(parseNewTopicDecision(result)).toBeNull();
    },
  );
});
