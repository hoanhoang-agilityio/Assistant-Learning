import type { AnswerKey, QuizQuestion } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  calculateMastery,
  calculatePercent,
  findWeakestConcept,
  gradeQuestions,
  scoreQuiz,
} from "@/features/agent/utils/scoring";

const OPTIONS = ["a", "b", "c", "d"];

const createQuestion = (id: string, concept: string): QuizQuestion => ({
  id,
  concept,
  question: `Question ${id}?`,
  options: OPTIONS,
});

const QUESTIONS = [
  createQuestion("q1", "Closures"),
  createQuestion("q2", "Scope"),
  createQuestion("q3", "Closures"),
  createQuestion("q4", "Hoisting"),
];

const KEY: AnswerKey = {
  correctIndex: [0, 1, 2, 3],
  explanations: ["", "", "", ""],
};

describe("calculatePercent", () => {
  it("rounds to a whole number", () => {
    expect(calculatePercent(1, 3)).toBe(33);
    expect(calculatePercent(2, 3)).toBe(67);
  });

  it("is 0 when there is nothing to count", () => {
    expect(calculatePercent(0, 0)).toBe(0);
  });
});

describe("gradeQuestions", () => {
  it("marks each answer against the key", () => {
    const results = gradeQuestions(QUESTIONS, { q1: 0, q2: 0 }, KEY);
    expect(results.map(({ isCorrect }) => isCorrect)).toEqual([
      true,
      false,
      false,
      false,
    ]);
    expect(results[1]?.correctIndex).toBe(1);
  });

  it("throws when the key is shorter than the quiz", () => {
    expect(() =>
      gradeQuestions(QUESTIONS, {}, { correctIndex: [0], explanations: [""] }),
    ).toThrow();
  });
});

describe("calculateMastery", () => {
  it("groups by concept in first-seen order", () => {
    const results = gradeQuestions(QUESTIONS, { q1: 0, q2: 1, q3: 0 }, KEY);
    expect(calculateMastery(QUESTIONS, results)).toEqual([
      { concept: "Closures", percent: 50 },
      { concept: "Scope", percent: 100 },
      { concept: "Hoisting", percent: 0 },
    ]);
  });
});

describe("findWeakestConcept", () => {
  it("picks the lowest percent", () => {
    expect(
      findWeakestConcept([
        { concept: "A", percent: 80 },
        { concept: "B", percent: 20 },
      ]),
    ).toBe("B");
  });

  it("picks the first concept on a tie", () => {
    expect(
      findWeakestConcept([
        { concept: "A", percent: 50 },
        { concept: "B", percent: 50 },
      ]),
    ).toBe("A");
  });

  it("is null with no concepts or a perfect score", () => {
    expect(findWeakestConcept([])).toBeNull();
    expect(findWeakestConcept([{ concept: "A", percent: 100 }])).toBeNull();
  });
});

describe("scoreQuiz", () => {
  it("scores a partly correct quiz", () => {
    const score = scoreQuiz(QUESTIONS, { q1: 0, q2: 1, q3: 0, q4: 0 }, KEY);
    expect(score).toMatchObject({
      correct: 2,
      total: 4,
      percent: 50,
      weakestConcept: "Hoisting",
    });
  });

  it("scores 0 answers as 0%", () => {
    const score = scoreQuiz(QUESTIONS, {}, KEY);
    expect(score.correct).toBe(0);
    expect(score.percent).toBe(0);
    expect(score.weakestConcept).toBe("Closures");
  });

  it("scores an empty quiz without dividing by zero", () => {
    const score = scoreQuiz([], {}, { correctIndex: [], explanations: [] });
    expect(score).toMatchObject({
      correct: 0,
      total: 0,
      percent: 0,
      weakestConcept: null,
    });
  });
});
