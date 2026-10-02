import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { applyClientEdits } from "../client-edits";

const QUIZ: Quiz = {
  id: "quiz-1",
  questions: ["q1", "q2"].map((id) => ({
    id,
    concept: "Closures",
    question: `${id}?`,
    options: ["a", "b", "c", "d"],
  })),
  answers: {},
  answerKeySealed: "sealed",
  submitted: false,
};

const QUIZZED: LearningState = {
  ...initialLearningState,
  stage: "quiz",
  topic: "Closures",
  material: { original: "# Notes", simplified: "# Easy", view: "original" },
  quiz: QUIZ,
};

const GRADED: LearningState = {
  ...QUIZZED,
  stage: "feedback",
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1 }, submitted: true },
  evaluation: {
    correct: 1,
    total: 2,
    percent: 50,
    weakestConcept: "Closures",
    perQuestion: [],
    mastery: [],
  },
  score: { percent: 50, tier: "Practitioner" },
  feedback: { a2uiOperations: [], summary: "Ok." },
};

describe("applyClientEdits", () => {
  it.each([undefined, null, {}, "state", { quiz: "x", material: 1 }])(
    "changes nothing for %j",
    (client) => {
      expect(applyClientEdits(QUIZZED, client)).toBe(QUIZZED);
    },
  );

  it("changes nothing when the browser sends the state back as it is", () => {
    expect(applyClientEdits(GRADED, GRADED)).toBe(GRADED);
  });

  it("never takes a key the server owns", () => {
    const next = applyClientEdits(QUIZZED, {
      ...QUIZZED,
      stage: "score",
      topic: "Forged",
      status: { running: "quiz" },
      score: { percent: 100, tier: "Master" },
      board: [{ id: "b", title: "b", operations: [], revision: 1 }],
      quizOutdated: true,
    });

    expect(next).toBe(QUIZZED);
  });

  describe("answers", () => {
    it("takes the answers for this quiz's questions only", () => {
      const next = applyClientEdits(QUIZZED, {
        quiz: { ...QUIZ, answers: { q1: 3, q9: 1 } },
      });

      expect(next.quiz).toEqual({ ...QUIZ, answers: { q1: 3 } });
    });

    it("takes nothing else from the browser's quiz", () => {
      const next = applyClientEdits(QUIZZED, {
        quiz: {
          id: QUIZ.id,
          answers: { q1: 3 },
          submitted: true,
          answerKeySealed: "forged",
          questions: [],
        },
      });

      expect(next.quiz).toEqual({ ...QUIZ, answers: { q1: 3 } });
    });

    it.each([
      ["another quiz", { quiz: { id: "quiz-0", answers: { q1: 3 } } }],
      [
        "an option that does not exist",
        { quiz: { id: "quiz-1", answers: { q1: 4 } } },
      ],
      ["no quiz", { quiz: null }],
    ])("ignores answers for %s", (_, client) => {
      expect(applyClientEdits(QUIZZED, client)).toBe(QUIZZED);
    });

    it("reads changed answers on a graded quiz as a retake", () => {
      const next = applyClientEdits(GRADED, {
        quiz: { ...GRADED.quiz, answers: { q1: 2 } },
      });

      expect(next).toMatchObject({
        stage: "quiz",
        quiz: { answers: { q1: 2 }, submitted: false },
        evaluation: null,
        score: null,
        feedback: null,
        reflection: null,
      });
    });

    it("reads a graded quiz sent back as not submitted as a retake, even with the same answers", () => {
      const next = applyClientEdits(GRADED, {
        quiz: { ...GRADED.quiz, submitted: false },
      });

      expect(next).toMatchObject({
        stage: "quiz",
        quiz: { answers: { q1: 0, q2: 1 }, submitted: false },
        evaluation: null,
        score: null,
      });
    });

    it("never grades a quiz the browser sends as submitted", () => {
      expect(
        applyClientEdits(QUIZZED, { quiz: { ...QUIZ, submitted: true } }),
      ).toBe(QUIZZED);
    });
  });

  describe("learning material", () => {
    it("takes an edit and clears the quiz written from the old text", () => {
      const next = applyClientEdits(QUIZZED, {
        material: { ...QUIZZED.material, original: "# Edited" },
      });

      expect(next).toMatchObject({
        stage: "material",
        material: { original: "# Edited", simplified: "# Easy" },
        quiz: null,
        quizOutdated: true,
      });
    });

    it("takes a change of view and keeps the quiz", () => {
      const next = applyClientEdits(QUIZZED, {
        material: { ...QUIZZED.material, view: "simplified" },
      });

      expect(next.material?.view).toBe("simplified");
      expect(next.quiz).toBe(QUIZZED.quiz);
    });

    it("cannot add a simplified version the server never wrote", () => {
      const state: LearningState = {
        ...QUIZZED,
        material: { original: "# Notes", simplified: null, view: "original" },
      };

      expect(
        applyClientEdits(state, {
          material: {
            original: "# Notes",
            simplified: "# Mine",
            view: "simplified",
          },
        }),
      ).toBe(state);
    });

    it("cannot create or remove the learning material", () => {
      const material = {
        original: "# Mine",
        simplified: null,
        view: "original",
      };

      expect(applyClientEdits(initialLearningState, { material })).toBe(
        initialLearningState,
      );
      expect(applyClientEdits(QUIZZED, { material: null })).toBe(QUIZZED);
    });
  });

  describe("reflection", () => {
    const reflection = { rating: 4, text: "Clear" };

    it("is saved once there is feedback", () => {
      expect(applyClientEdits(GRADED, { reflection }).reflection).toEqual(
        reflection,
      );
    });

    it("is ignored without feedback, or when it is not a reflection", () => {
      expect(applyClientEdits(QUIZZED, { reflection })).toBe(QUIZZED);
      expect(applyClientEdits(GRADED, { reflection: { rating: 9 } })).toBe(
        GRADED,
      );
    });

    it("is cleared with the results it was about", () => {
      const next = applyClientEdits(
        { ...GRADED, reflection },
        { reflection, quiz: { ...GRADED.quiz, answers: {} } },
      );

      expect(next.reflection).toBeNull();
    });
  });
});
