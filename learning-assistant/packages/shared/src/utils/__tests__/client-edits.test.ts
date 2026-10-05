import { describe, expect, it } from "vitest";

import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "../../schemas";
import {
  applyMaterialEdit,
  replaceMaterial,
  retakeQuiz,
  setMaterialView,
} from "../client-edits";

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

describe("replaceMaterial", () => {
  it("treats a change of view alone as no edit", () => {
    const state: LearningState = {
      ...withResults,
      material: { original: "# Notes", simplified: "# Easy", view: "original" },
    };
    const next = replaceMaterial(state, {
      original: "# Notes",
      simplified: "# Easy",
      view: "simplified",
    });

    expect(next.material?.view).toBe("simplified");
    expect(next.quiz).toBe(state.quiz);
    expect(next.quizOutdated).toBe(false);
  });

  it("clears the quiz when either text differs", () => {
    const next = replaceMaterial(withResults, {
      original: "# Rewritten",
      simplified: null,
      view: "original",
    });

    expect(next).toMatchObject({ quiz: null, score: null, quizOutdated: true });
    expect(next.stage).toBe("material");
  });

  it("returns the same state when nothing changed or there is nothing to replace", () => {
    const { material } = withMaterial;
    if (!material) {
      throw new Error("The fixture has no learning material.");
    }

    expect(replaceMaterial(withMaterial, { ...material })).toBe(withMaterial);
    expect(replaceMaterial(initialLearningState, material)).toBe(
      initialLearningState,
    );
  });
});

describe("retakeQuiz", () => {
  const QUIZ: Quiz = {
    id: "quiz-1",
    questions: [
      {
        id: "q1",
        concept: "A",
        question: "One?",
        options: ["a", "b", "c", "d"],
      },
    ],
    answers: { q1: 0 },
    answerKeySealed: "sealed",
    submitted: true,
  };

  it("clears the answers and the results, keeps the questions", () => {
    const next = retakeQuiz({ ...withResults, quiz: QUIZ });

    expect(next.quiz).toEqual({ ...QUIZ, answers: {}, submitted: false });
    expect(next).toMatchObject({
      stage: "quiz",
      evaluation: null,
      score: null,
      feedback: null,
    });
  });

  it("returns the same state without a quiz", () => {
    expect(retakeQuiz(initialLearningState)).toBe(initialLearningState);
  });
});
