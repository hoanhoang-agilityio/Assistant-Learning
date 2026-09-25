import type { Quiz, QuizDraft } from "@repo/shared/schemas";

import { QUESTION_ID_PREFIX } from "../../constants/answer-key";
import type { AnswerKeyStore } from "../../types/answer-key";

/**
 * Turns a Quiz Agent draft into the quiz written to state: server-made ids,
 * the public part of each question picked field by field, and the answers
 * and explanations sealed into `answerKeySealed`. Nothing else of the draft
 * reaches the client.
 */
export const createSealedQuiz = async (
  draft: QuizDraft,
  answerKeys: AnswerKeyStore,
  createId: () => string = () => crypto.randomUUID(),
): Promise<Quiz> => {
  const id = createId();
  const answerKeySealed = await answerKeys.seal(id, {
    correctIndex: draft.questions.map(({ correctIndex }) => correctIndex),
    explanations: draft.questions.map(({ explanation }) => explanation),
  });

  return {
    id,
    questions: draft.questions.map(({ concept, question, options }, index) => ({
      id: `${QUESTION_ID_PREFIX}${index + 1}`,
      concept,
      question,
      options,
    })),
    answers: {},
    answerKeySealed,
    submitted: false,
  };
};
