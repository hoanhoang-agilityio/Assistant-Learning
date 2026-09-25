import type { QuizQuestion } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { createGradedQuestions, mergeExplanations } from "../evaluation";

const QUESTIONS: QuizQuestion[] = [
  {
    id: "a",
    concept: "Closures",
    question: "A?",
    options: ["1", "2", "3", "4"],
  },
  { id: "b", concept: "Scope", question: "B?", options: ["1", "2", "3", "4"] },
];

const RESULTS = [
  { qid: "a", correctIndex: 1, isCorrect: true },
  { qid: "b", correctIndex: 2, isCorrect: false },
];

describe("createGradedQuestions", () => {
  it("joins each question with the answer, grade and key explanation", () => {
    const graded = createGradedQuestions(QUESTIONS, { a: 1, b: 0 }, RESULTS, [
      "key a",
      "key b",
    ]);

    expect(graded[1]).toEqual({
      qid: "b",
      concept: "Scope",
      question: "B?",
      options: ["1", "2", "3", "4"],
      chosenIndex: 0,
      correctIndex: 2,
      isCorrect: false,
      keyExplanation: "key b",
    });
  });

  it("marks an unanswered question and a missing key explanation", () => {
    const [graded] = createGradedQuestions(QUESTIONS, {}, RESULTS, []);

    expect(graded).toMatchObject({ chosenIndex: null, keyExplanation: "" });
  });

  it("throws when the grades do not line up with the questions", () => {
    expect(() =>
      createGradedQuestions(QUESTIONS, {}, [...RESULTS].reverse(), []),
    ).toThrow("Question a has no grade.");
  });
});

describe("mergeExplanations", () => {
  const graded = createGradedQuestions(QUESTIONS, { a: 1, b: 0 }, RESULTS, [
    "key a",
    "key b",
  ]);

  it("uses the Evaluator's explanation for each question it wrote", () => {
    expect(
      mergeExplanations(graded, [
        { qid: "b", explanation: " Evaluator b " },
        { qid: "unknown", explanation: "ignored" },
      ]),
    ).toEqual([
      { qid: "a", correctIndex: 1, isCorrect: true, explanation: "key a" },
      {
        qid: "b",
        correctIndex: 2,
        isCorrect: false,
        explanation: "Evaluator b",
      },
    ]);
  });

  it("falls back to the answer key without Evaluator output", () => {
    expect(
      mergeExplanations(graded).map(({ explanation }) => explanation),
    ).toEqual(["key a", "key b"]);
  });

  it("falls back to the answer key for a blank explanation", () => {
    expect(
      mergeExplanations(graded, [{ qid: "a", explanation: "   " }])[0]
        ?.explanation,
    ).toBe("key a");
  });
});
