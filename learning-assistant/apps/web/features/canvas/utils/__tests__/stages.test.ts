import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  calculateStageProgress,
  getAdjacentStage,
  getFollowedStage,
  getRunningStage,
  getStepperSteps,
  isStageBuilding,
  isStageUnlocked,
  toCanvasStage,
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
  material: { original: "# Notes", simplified: null, view: "original" },
  stage: "material",
  status: { running: "quiz" },
};

describe("toCanvasStage", () => {
  it("maps idle to no stage and keeps the rest", () => {
    expect(toCanvasStage("idle")).toBeNull();
    expect(toCanvasStage("feedback")).toBe("feedback");
  });
});

describe("getRunningStage", () => {
  it("maps each running task to its stage", () => {
    expect(getRunningStage(initialLearningState)).toBeNull();
    expect(
      getRunningStage({
        ...initialLearningState,
        status: { running: "simplify" },
      }),
    ).toBe("material");
    expect(getRunningStage(withQuizRunning)).toBe("quiz");
  });
});

describe("isStageBuilding", () => {
  it("covers every stage an evaluate draft fills", () => {
    const evaluating: LearningState = {
      ...withQuizRunning,
      status: { running: "evaluate" },
      draft: {
        task: "evaluate",
        evaluation: {
          correct: 1,
          total: 1,
          percent: 100,
          weakestConcept: null,
          perQuestion: [],
          mastery: [],
        },
        score: { percent: 100, tier: "Master" },
        feedback: { a2uiOperations: [], summary: "" },
      },
    };

    for (const stage of ["evaluation", "score", "feedback"] as const) {
      expect(isStageBuilding(evaluating, stage)).toBe(true);
      expect(isStageUnlocked(evaluating, stage)).toBe(true);
    }
    expect(isStageBuilding(evaluating, "quiz")).toBe(false);
  });

  it("covers only the running stage before a draft arrives", () => {
    const evaluating = {
      ...withQuizRunning,
      status: { running: "evaluate" as const },
    };

    expect(isStageBuilding(evaluating, "evaluation")).toBe(true);
    expect(isStageUnlocked(evaluating, "feedback")).toBe(false);
  });
});

describe("isStageUnlocked", () => {
  it("unlocks a stage once its data exists", () => {
    expect(isStageUnlocked(initialLearningState, "research")).toBe(false);
    expect(isStageUnlocked(withResearch, "research")).toBe(true);
    expect(isStageUnlocked(withResearch, "material")).toBe(false);
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
    expect(getAdjacentStage(withQuizRunning, "research", "next")).toBe(
      "material",
    );
    expect(getAdjacentStage(withQuizRunning, "quiz", "prev")).toBe("material");
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
    const steps = getStepperSteps(withQuizRunning, "material");
    const flags = Object.fromEntries(
      steps.map(({ id, isActive, isUnlocked, isCompleted, isBuilding }) => [
        id,
        { isActive, isUnlocked, isCompleted, isBuilding },
      ]),
    );

    expect(steps.map(({ id }) => id)).toEqual([
      "research",
      "material",
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
    expect(flags.material).toEqual({
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
