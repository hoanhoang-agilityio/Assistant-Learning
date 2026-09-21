import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  calculateStageProgress,
  getAdjacentStage,
  getFollowedStage,
  getRunningStage,
  getStepperSteps,
  isStageUnlocked,
} from "@/features/canvas/utils/stages";

const research: LearningState["research"] = {
  title: "Closures",
  summary: "Functions that remember their scope.",
  keyInsight: "A closure keeps its bindings alive.",
  keyTerms: [],
  sources: [],
};

const withResearch: LearningState = {
  ...initialLearningState,
  stage: "research",
  topic: "Closures",
  research,
};

const withQuizRunning: LearningState = {
  ...withResearch,
  notes: { original: "# Notes", simplified: null, view: "original" },
  stage: "notes",
  status: { running: "quiz" },
};

describe("getRunningStage", () => {
  it("maps each running task to its stage", () => {
    expect(getRunningStage(initialLearningState)).toBeNull();
    expect(
      getRunningStage({
        ...initialLearningState,
        status: { running: "simplify" },
      }),
    ).toBe("notes");
    expect(getRunningStage(withQuizRunning)).toBe("quiz");
  });
});

describe("isStageUnlocked", () => {
  it("unlocks a stage once its data exists", () => {
    expect(isStageUnlocked(initialLearningState, "research")).toBe(false);
    expect(isStageUnlocked(withResearch, "research")).toBe(true);
    expect(isStageUnlocked(withResearch, "notes")).toBe(false);
  });

  it("unlocks the stage that is being built", () => {
    expect(isStageUnlocked(withQuizRunning, "quiz")).toBe(true);
  });
});

describe("getFollowedStage", () => {
  it("is null before any work", () => {
    expect(getFollowedStage(initialLearningState)).toBeNull();
  });

  it("follows the finished stage", () => {
    expect(getFollowedStage(withResearch)).toBe("research");
  });

  it("prefers the running stage", () => {
    expect(getFollowedStage(withQuizRunning)).toBe("quiz");
  });
});

describe("getAdjacentStage", () => {
  it("skips to the nearest unlocked stage", () => {
    expect(getAdjacentStage(withQuizRunning, "research", "next")).toBe("notes");
    expect(getAdjacentStage(withQuizRunning, "quiz", "prev")).toBe("notes");
  });

  it("returns null at either end", () => {
    expect(getAdjacentStage(withResearch, "research", "prev")).toBeNull();
    expect(getAdjacentStage(withResearch, "research", "next")).toBeNull();
  });
});

describe("calculateStageProgress", () => {
  it("fills up to the last unlocked stage", () => {
    expect(calculateStageProgress(initialLearningState)).toBe(0);
    expect(calculateStageProgress(withResearch)).toBe(0);
    // Quiz is the third of six stages: 2 / 5 of the bar.
    expect(calculateStageProgress(withQuizRunning)).toBe(40);
  });
});

describe("getStepperSteps", () => {
  it("flags each stage from the state and the active stage", () => {
    const steps = getStepperSteps(withQuizRunning, "notes");
    const flags = Object.fromEntries(
      steps.map(({ id, isActive, isUnlocked, isCompleted, isBuilding }) => [
        id,
        { isActive, isUnlocked, isCompleted, isBuilding },
      ]),
    );

    expect(steps.map(({ id }) => id)).toEqual([
      "research",
      "notes",
      "quiz",
      "evaluation",
      "score",
      "feedback",
    ]);
    expect(flags.research).toEqual({
      isActive: false,
      isUnlocked: true,
      isCompleted: true,
      isBuilding: false,
    });
    expect(flags.notes).toEqual({
      isActive: true,
      isUnlocked: true,
      isCompleted: false,
      isBuilding: false,
    });
    expect(flags.quiz).toEqual({
      isActive: false,
      isUnlocked: true,
      isCompleted: false,
      isBuilding: true,
    });
    expect(flags.evaluation?.isUnlocked).toBe(false);
  });
});
