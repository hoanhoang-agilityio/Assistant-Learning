import type { AnswerKey } from "@repo/shared/schemas";

/**
 * Keeps a quiz's answer key away from the client until the quiz is graded.
 * v1 seals it into state (`quiz.answerKeySealed`); v2 stores it in the
 * database and the token becomes a row reference.
 */
export interface AnswerKeyStore {
  /** Returns the token written to `quiz.answerKeySealed`. */
  seal: (quizId: string, key: AnswerKey) => Promise<string>;
  /** Throws when the token is not a valid key for this quiz. */
  unseal: (quizId: string, token: string) => Promise<AnswerKey>;
}
