import type { Tier } from "@repo/shared/schemas";

import type { QuizScore } from "../types/scoring";

/**
 * A plain feedback summary written from the score alone. It is the fallback
 * text for the Feedback stage when the Evaluator Agent writes none.
 */
export const formatFeedbackSummary = (
  { correct, total, percent, weakestConcept }: QuizScore,
  tier: Tier,
): string => {
  const result = `You answered ${correct} of ${total} questions correctly (${percent}%), which puts you at the ${tier} tier.`;
  const next = weakestConcept
    ? `Review "${weakestConcept}" in your learning material next.`
    : "You got every concept right.";
  return `${result} ${next}`;
};
