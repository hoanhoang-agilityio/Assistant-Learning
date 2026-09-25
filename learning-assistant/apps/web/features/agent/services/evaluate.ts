import type {
  EvaluationFeedback,
  Quiz,
  ToolResultData,
} from "@repo/shared/schemas";
import { getTier } from "@repo/shared/utils/tier";
import type { DeepPartial } from "ai";

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
import type { RunSettings } from "@/types/llm";

interface EvaluateParams {
  quiz: Quiz;
  /** Every question's chosen option, already checked by `validateSubmission`. */
  answers: Quiz["answers"];
  answerKeys: AnswerKeyStore;
  /** The learning material the student was quizzed on. */
  material: string;
  settings: RunSettings;
  signal?: AbortSignal;
  /**
   * Streams the grading: called with the whole evaluation and score as soon
   * as they are graded, then again as the explanations, the summary and the
   * Feedback surface are written.
   */
  onDraft?: (draft: Omit<ToolResultData<"evaluate">, "answers">) => void;
}

/** The explanations written so far that are complete enough to show. */
const toWrittenExplanations = (
  partial: DeepPartial<EvaluationFeedback> | null,
): EvaluationFeedback["explanations"] =>
  (partial?.explanations ?? []).flatMap((item) =>
    item?.qid && item.explanation
      ? [{ qid: item.qid, explanation: item.explanation }]
      : [],
  );

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
 * the score take its place. With `onDraft`, both calls stream.
 */
export const runEvaluation = async ({
  quiz,
  answers,
  answerKeys,
  material,
  settings,
  signal,
  onDraft,
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
    material,
  };

  const toResult = (
    written: DeepPartial<EvaluationFeedback> | null,
    a2uiOperations: unknown[],
    summary: string,
  ) => ({
    evaluation: {
      correct: score.correct,
      total: score.total,
      percent: score.percent,
      weakestConcept: score.weakestConcept,
      perQuestion: mergeExplanations(
        input.questions,
        toWrittenExplanations(written),
      ),
      mastery: score.mastery,
    },
    score: { percent: score.percent, tier },
    feedback: { a2uiOperations, summary },
  });

  // Both calls stream into one draft, sent whole each time.
  let partial: DeepPartial<EvaluationFeedback> | null = null;
  let draftOperations: unknown[] = [];
  const reportDraft = () =>
    onDraft?.(toResult(partial, draftOperations, partial?.summary ?? ""));
  reportDraft();

  const [written, a2uiOperations] = await Promise.all([
    runOrFallback(
      "Explanations",
      () =>
        runEvaluator({
          input,
          settings,
          signal,
          onPartial: onDraft
            ? (next) => {
                partial = next;
                reportDraft();
              }
            : undefined,
        }),
      null,
      signal,
    ),
    runOrFallback(
      "Feedback surface",
      () =>
        runFeedbackSurface({
          input,
          settings,
          signal,
          onDraft: onDraft
            ? (operations) => {
                draftOperations = operations;
                reportDraft();
              }
            : undefined,
        }),
      [],
      signal,
    ),
  ]);

  return {
    answers,
    ...toResult(
      written,
      a2uiOperations,
      written?.summary.trim() || formatFeedbackSummary(score, tier),
    ),
  };
};
