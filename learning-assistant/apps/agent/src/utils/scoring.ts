import type { AnswerKey, Evaluation, QuizQuestion } from "@repo/shared/schemas";

import type { QuestionResult, QuizScore } from "../types/scoring";

/** Whole-number percent; 0 when there is nothing to count. */
export const calculatePercent = (part: number, whole: number): number =>
  whole === 0 ? 0 : Math.round((part / whole) * 100);

/** Each question against the key; an unanswered question is wrong. */
export const gradeQuestions = (
  questions: readonly QuizQuestion[],
  answers: Readonly<Record<string, number>>,
  key: AnswerKey,
): QuestionResult[] =>
  questions.map(({ id }, index) => {
    const correctIndex = key.correctIndex[index];
    if (correctIndex === undefined) {
      throw new Error(`The answer key has no answer for question ${id}.`);
    }
    return { qid: id, correctIndex, isCorrect: answers[id] === correctIndex };
  });

/** Percent correct for each concept, in the order concepts first appear. */
export const calculateMastery = (
  questions: readonly QuizQuestion[],
  results: readonly QuestionResult[],
): Evaluation["mastery"] => {
  const counts = new Map<string, { correct: number; total: number }>();
  questions.forEach(({ concept }, index) => {
    const count = counts.get(concept) ?? { correct: 0, total: 0 };
    count.total += 1;
    if (results[index]?.isCorrect) {
      count.correct += 1;
    }
    counts.set(concept, count);
  });
  return Array.from(counts, ([concept, { correct, total }]) => ({
    concept,
    percent: calculatePercent(correct, total),
  }));
};

/**
 * The concept with the lowest mastery; on a tie, the one asked first. `null`
 * when there are no concepts or every concept was answered perfectly.
 */
export const findWeakestConcept = (
  mastery: Evaluation["mastery"],
): string | null => {
  const weakest = mastery.reduce<Evaluation["mastery"][number] | null>(
    (lowest, entry) =>
      lowest === null || entry.percent < lowest.percent ? entry : lowest,
    null,
  );
  return weakest && weakest.percent < 100 ? weakest.concept : null;
};

/** Everything about a graded quiz that code can work out. */
export const scoreQuiz = (
  questions: readonly QuizQuestion[],
  answers: Readonly<Record<string, number>>,
  key: AnswerKey,
): QuizScore => {
  const perQuestion = gradeQuestions(questions, answers, key);
  const correct = perQuestion.filter(({ isCorrect }) => isCorrect).length;
  const mastery = calculateMastery(questions, perQuestion);

  return {
    correct,
    total: questions.length,
    percent: calculatePercent(correct, questions.length),
    perQuestion,
    mastery,
    weakestConcept: findWeakestConcept(mastery),
  };
};
