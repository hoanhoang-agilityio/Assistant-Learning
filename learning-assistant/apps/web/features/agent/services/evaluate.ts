import type { Quiz, Settings, ToolResultData } from "@repo/shared/schemas";
import { getTier } from "@repo/shared/utils/tier";

import { runEvaluator } from "@/features/agent/services/subagents/evaluator";
import { runFeedbackSurface } from "@/features/agent/services/subagents/feedback-surface";
import type { AnswerKeyStore } from "@/features/agent/types/answer-key";
import type { EvaluatorInput } from "@/features/agent/types/scoring";
import {
  createGradedQuestions,
  mergeExplanations,
} from "@/features/agent/utils/evaluation";
import { formatFeedbackSummary } from "@/features/agent/utils/feedback-summary";
import { scoreQuiz } from "@/features/agent/utils/scoring";

interface EvaluateParams {
  quiz: Quiz;
  /** Every question's chosen option, already checked by `validateSubmission`. */
  answers: Quiz["answers"];
  answerKeys: AnswerKeyStore;
  /** The notes the student was quizzed on. */
  notes: string;
  settings: Settings;
  signal?: AbortSignal;
}

/**
 * Runs one Evaluator call and returns `fallback` if it fails, so a model
 * error never costs the student their grade. A stop still stops.
 */
const runOrFallback = async <T>(
  label: string,
  work: () => Promise<T>,
  fallback: T,
  signal?: AbortSignal,
): Promise<T> => {
  try {
    return await work();
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    console.warn(`[evaluate] ${label} failed; using the fallback.`, error);
    return fallback;
  }
};

/**
 * The evaluate pipeline: unseal the answer key (the only place it is
 * unsealed) and grade in code, then ask the Evaluator Agent, in parallel, for
 * the explanations and summary, and for the dynamic Feedback surface. When
 * either call fails, the answer key's explanations and a summary written from
 * the score take its place.
 */
export const runEvaluation = async ({
  quiz,
  answers,
  answerKeys,
  notes,
  settings,
  signal,
}: EvaluateParams): Promise<ToolResultData<"evaluate">> => {
  const key = await answerKeys.unseal(quiz.id, quiz.answerKeySealed);
  const score = scoreQuiz(quiz.questions, answers, key);
  const tier = getTier(score.percent);
  const input: EvaluatorInput = {
    questions: createGradedQuestions(
      quiz.questions,
      answers,
      score.perQuestion,
      key.explanations,
    ),
    score,
    tier,
    notes,
  };

  const [written, a2uiOperations] = await Promise.all([
    runOrFallback(
      "Explanations",
      () => runEvaluator({ input, settings, signal }),
      null,
      signal,
    ),
    runOrFallback(
      "Feedback surface",
      () => runFeedbackSurface({ input, settings, signal }),
      [],
      signal,
    ),
  ]);

  return {
    answers,
    evaluation: {
      correct: score.correct,
      total: score.total,
      percent: score.percent,
      weakestConcept: score.weakestConcept,
      perQuestion: mergeExplanations(input.questions, written?.explanations),
      mastery: score.mastery,
    },
    score: { percent: score.percent, tier },
    feedback: {
      a2uiOperations,
      summary: written?.summary.trim() || formatFeedbackSummary(score, tier),
    },
  };
};
