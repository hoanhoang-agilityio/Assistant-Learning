import type {
  Evaluation,
  EvaluationFeedback,
  QuizQuestion,
} from "@repo/shared/schemas";

import type { GradedQuestion, QuestionResult } from "../types/scoring";

/**
 * Joins each question with the student's answer, its grade and the answer
 * key's explanation, in quiz order.
 */
export const createGradedQuestions = (
  questions: readonly QuizQuestion[],
  answers: Readonly<Record<string, number>>,
  results: readonly QuestionResult[],
  keyExplanations: readonly string[],
): GradedQuestion[] =>
  questions.map(({ id, concept, question, options }, index) => {
    const result = results[index];
    if (!result || result.qid !== id) {
      throw new Error(`Question ${id} has no grade.`);
    }
    return {
      qid: id,
      concept,
      question,
      options,
      chosenIndex: answers[id] ?? null,
      correctIndex: result.correctIndex,
      isCorrect: result.isCorrect,
      keyExplanation: keyExplanations[index] ?? "",
    };
  });

/**
 * The per-question results written to state: the Evaluator's explanation for
 * each question, or the answer key's when it wrote none (or failed).
 */
export const mergeExplanations = (
  questions: readonly GradedQuestion[],
  explanations: EvaluationFeedback["explanations"] = [],
): Evaluation["perQuestion"] => {
  const written = new Map(
    explanations.map(({ qid, explanation }) => [qid, explanation.trim()]),
  );
  return questions.map(({ qid, correctIndex, isCorrect, keyExplanation }) => ({
    qid,
    correctIndex,
    isCorrect,
    explanation: written.get(qid) || keyExplanation,
  }));
};
