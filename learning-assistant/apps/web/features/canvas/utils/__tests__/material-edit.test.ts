import { initialLearningState, type LearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  applyMaterialEdit,
  setMaterialView,
} from "@/features/canvas/utils/material-edit";

const withMaterial: LearningState = {
  ...initialLearningState,
  stage: "material",
  material: { original: "# Notes", simplified: null, view: "original" },
};

const withResults: LearningState = {
  ...withMaterial,
  stage: "score",
  quiz: {
    id: "q1",
    questions: [],
    answers: {},
    answerKeySealed: "sealed",
    submitted: true,
  },
  evaluation: {
    correct: 1,
    total: 1,
    percent: 100,
    weakestConcept: null,
    perQuestion: [],
    mastery: [],
  },
  score: { percent: 100, tier: "Master" },
  feedback: { a2uiOperations: [], summary: "Great" },
  reflection: { rating: 5, text: "Fun" },
};

describe("applyMaterialEdit", () => {
  it("writes the original learning material when that view is active", () => {
    const next = applyMaterialEdit(withMaterial, "# Edited");
    expect(next.material).toEqual({
      ...withMaterial.material,
      original: "# Edited",
    });
  });

  it("writes the simplified learning material when that view is active", () => {
    const state: LearningState = {
      ...withMaterial,
      material: {
        original: "# Notes",
        simplified: "# Easy",
        view: "simplified",
      },
    };
    const next = applyMaterialEdit(state, "# Easier");
    expect(next.material).toEqual({
      original: "# Notes",
      simplified: "# Easier",
      view: "simplified",
    });
  });

  it("clears the quiz and everything built from it", () => {
    const next = applyMaterialEdit(withResults, "# Edited");
    expect(next).toMatchObject({
      quiz: null,
      evaluation: null,
      score: null,
      feedback: null,
      reflection: null,
      quizOutdated: true,
    });
  });

  it("moves a later stage back to learning material", () => {
    expect(applyMaterialEdit(withResults, "# Edited").stage).toBe("material");
  });

  it("does not flag the quiz as outdated when there was none", () => {
    const next = applyMaterialEdit(withMaterial, "# Edited");
    expect(next.quizOutdated).toBe(false);
    expect(next.stage).toBe("material");
  });

  it("keeps the outdated flag set on later edits", () => {
    const once = applyMaterialEdit(withResults, "# Edited");
    expect(applyMaterialEdit(once, "# Edited again").quizOutdated).toBe(true);
  });

  it("returns the same state when the text did not change", () => {
    expect(applyMaterialEdit(withResults, "# Notes")).toBe(withResults);
  });

  it("returns the same state when there is no learning material", () => {
    expect(applyMaterialEdit(initialLearningState, "x")).toBe(
      initialLearningState,
    );
  });
});

describe("setMaterialView", () => {
  it("switches the view and keeps the quiz", () => {
    const next = setMaterialView(withResults, "simplified");
    expect(next.material?.view).toBe("simplified");
    expect(next.quiz).toBe(withResults.quiz);
  });
});
