import type { Evaluation, QuizQuestion } from "../schemas";

/** One concept's results in one graded attempt. */
export interface ConceptResult {
  key: string;
  concept: string;
  correct: number;
  total: number;
}

/**
 * The name a concept is kept under: quizzes write the same idea as
 * "Closures", "closures " or "Closures".
 */
export const toConceptKey = (concept: string): string =>
  concept.trim().replace(/\s+/g, " ").toLowerCase();

/** A whole percent of `correct` out of `total`; 0 without questions. */
export const calculateConceptPercent = (
  correct: number,
  total: number,
): number => (total > 0 ? Math.round((correct / total) * 100) : 0);

/**
 * How many questions on each concept a graded attempt had right, from its
 * questions (how many per concept) and its mastery (the percent of those
 * that were right). Concepts that differ only in case or spacing count as
 * one.
 */
export const countConceptResults = (
  questions: readonly Pick<QuizQuestion, "concept">[],
  mastery: Evaluation["mastery"],
): ConceptResult[] => {
  const percents = new Map(
    mastery.map(({ concept, percent }) => [toConceptKey(concept), percent]),
  );
  const results = new Map<string, ConceptResult>();

  for (const { concept } of questions) {
    const key = toConceptKey(concept);
    const result = results.get(key) ?? { key, concept, correct: 0, total: 0 };
    result.total += 1;
    results.set(key, result);
  }

  return Array.from(results.values(), (result) => ({
    ...result,
    correct: Math.round(((percents.get(result.key) ?? 0) / 100) * result.total),
  }));
};
