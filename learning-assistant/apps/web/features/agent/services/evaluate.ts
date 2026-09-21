import type { Quiz, ToolResultData } from "@repo/shared/schemas";

import type { AnswerKeyStore } from "@/features/agent/types/answer-key";
import { formatFeedbackSummary } from "@/features/agent/utils/feedback-summary";
import { getTier, scoreQuiz } from "@/features/agent/utils/scoring";

interface EvaluateParams {
  quiz: Quiz;
  /** Every question's chosen option, already checked by `validateSubmission`. */
  answers: Quiz["answers"];
  answerKeys: AnswerKeyStore;
}

/**
 * The evaluate pipeline: unseal the answer key (the only place it is
 * unsealed), score in code, and attach the explanations the Quiz Agent wrote.
 * TODO(M5.2, M5.3): the Evaluator Agent replaces the explanations and the
 * summary, and composes the dynamic Feedback surface (`a2uiOperations`).
 */
export const runEvaluation = async ({
  quiz,
  answers,
  answerKeys,
}: EvaluateParams): Promise<ToolResultData<"evaluate">> => {
  const key = await answerKeys.unseal(quiz.id, quiz.answerKeySealed);
  const score = scoreQuiz(quiz.questions, answers, key);
  const tier = getTier(score.percent);

  return {
    answers,
    evaluation: {
      correct: score.correct,
      total: score.total,
      percent: score.percent,
      weakestConcept: score.weakestConcept,
      perQuestion: score.perQuestion.map((result, index) => ({
        ...result,
        explanation: key.explanations[index] ?? "",
      })),
      mastery: score.mastery,
    },
    score: { percent: score.percent, tier },
    feedback: {
      a2uiOperations: [],
      summary: formatFeedbackSummary(score, tier),
    },
  };
};
