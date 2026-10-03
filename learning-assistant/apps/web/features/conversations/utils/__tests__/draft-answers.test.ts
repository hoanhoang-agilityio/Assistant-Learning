import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  applyDraftAnswers,
  toDraftAnswers,
} from "@/features/conversations/utils/draft-answers";

const QUIZ: Quiz = {
  id: "quiz_1",
  questions: [
    { id: "q1", concept: "Scope", question: "Q1?", options: ["a", "b"] },
    { id: "q2", concept: "Scope", question: "Q2?", options: ["a", "b"] },
  ],
  answers: { q1: 0 },
  answerKeySealed: "sealed",
  submitted: false,
};

const QUIZZED: LearningState = {
  ...initialLearningState,
  stage: "quiz",
  quiz: QUIZ,
};

const GRADED: LearningState = {
  ...QUIZZED,
  stage: "evaluation",
  quiz: { ...QUIZ, answers: { q1: 0, q2: 1 }, submitted: true },
  score: { percent: 50, tier: "Practitioner" },
};

describe("toDraftAnswers", () => {
  it("keeps the answers to a quiz not graded yet", () => {
    expect(toDraftAnswers(QUIZZED)).toEqual({
      quizId: QUIZ.id,
      answers: { q1: 0 },
    });
  });

  it("keeps nothing without a quiz or once it is graded", () => {
    expect(toDraftAnswers(initialLearningState)).toBeNull();
    expect(toDraftAnswers(GRADED)).toBeNull();
  });
});

describe("applyDraftAnswers", () => {
  it("puts the kept answers back on the same quiz", () => {
    const next = applyDraftAnswers(QUIZZED, {
      quizId: QUIZ.id,
      answers: { q1: 1, q2: 0 },
    });

    expect(next.quiz).toEqual({ ...QUIZ, answers: { q1: 1, q2: 0 } });
  });

  it("keeps only answers to the quiz's questions, with options that exist", () => {
    const next = applyDraftAnswers(QUIZZED, {
      quizId: QUIZ.id,
      answers: { q1: 1, q2: 7, q9: 0 },
    });

    expect(next.quiz?.answers).toEqual({ q1: 1 });
  });

  it("reads a draft on a graded quiz as a retake in progress", () => {
    const next = applyDraftAnswers(GRADED, {
      quizId: QUIZ.id,
      answers: { q2: 0 },
    });

    expect(next).toMatchObject({
      stage: "quiz",
      quiz: { answers: { q2: 0 }, submitted: false },
      score: null,
    });
  });

  it.each([
    ["no quiz", initialLearningState, { quizId: QUIZ.id, answers: {} }],
    ["another quiz", QUIZZED, { quizId: "quiz_0", answers: { q1: 1 } }],
    ["the same answers", QUIZZED, { quizId: QUIZ.id, answers: { q1: 0 } }],
  ])("changes nothing for %s", (_, state, draft) => {
    expect(applyDraftAnswers(state, draft)).toBe(state);
  });
});
