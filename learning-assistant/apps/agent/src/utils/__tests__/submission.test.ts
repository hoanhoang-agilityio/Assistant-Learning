import {
  initialLearningState,
  type LearningState,
  type Quiz,
} from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { TOOL_ERRORS } from "../../constants/tools";
import { validateSubmission } from "../submission";

const OPTIONS = ["a", "b", "c", "d"];

const QUIZ: Quiz = {
  id: "quiz-1",
  questions: [
    { id: "q1", concept: "A", question: "One?", options: OPTIONS },
    { id: "q2", concept: "B", question: "Two?", options: OPTIONS },
  ],
  answers: { q1: 0, q2: 3 },
  answerKeySealed: "sealed",
  submitted: false,
};

const withQuiz = (quiz: Partial<Quiz> = {}): LearningState => ({
  ...initialLearningState,
  quiz: { ...QUIZ, ...quiz },
});

describe("validateSubmission", () => {
  it("fails without a quiz", () => {
    expect(validateSubmission(initialLearningState)).toEqual({
      ok: false,
      error: TOOL_ERRORS.noQuiz,
    });
  });

  it("fails when the quiz was already graded", () => {
    expect(validateSubmission(withQuiz({ submitted: true }))).toEqual({
      ok: false,
      error: TOOL_ERRORS.quizAlreadySubmitted,
    });
  });

  it("fails when the answers are for another quiz", () => {
    const result = validateSubmission(withQuiz(), {
      quizId: "quiz-0",
      answers: { q1: 0, q2: 1 },
    });
    expect(result).toEqual({ ok: false, error: TOOL_ERRORS.staleQuiz });
  });

  it("fails when a question is unanswered", () => {
    const result = validateSubmission(withQuiz({ answers: { q1: 0 } }));
    expect(result.ok).toBe(false);
    expect(!result.ok && result.error).toContain("1 of 2");
  });

  it("uses the answers in state without a submission", () => {
    const result = validateSubmission(withQuiz());
    expect(result).toMatchObject({ ok: true, answers: { q1: 0, q2: 3 } });
  });

  it("prefers the submitted answers and drops unknown questions", () => {
    const result = validateSubmission(withQuiz({ answers: {} }), {
      quizId: QUIZ.id,
      answers: { q1: 2, q2: 1, q9: 0 },
    });
    expect(result).toMatchObject({ ok: true, answers: { q1: 2, q2: 1 } });
  });
});
