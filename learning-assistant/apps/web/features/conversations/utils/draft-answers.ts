import type { DraftAnswers, LearningState } from "@repo/shared/schemas";
import { retakeQuiz } from "@repo/shared/utils/client-edits";

const isSameAnswers = (
  a: DraftAnswers["answers"],
  b: DraftAnswers["answers"],
): boolean => {
  const ids = Object.keys(a);
  return (
    ids.length === Object.keys(b).length && ids.every((id) => a[id] === b[id])
  );
};

/** What to keep between runs: the answers to a quiz not graded yet, else `null`. */
export const toDraftAnswers = ({ quiz }: LearningState): DraftAnswers | null =>
  quiz && !quiz.submitted ? { quizId: quiz.id, answers: quiz.answers } : null;

/**
 * Puts kept answers back after a reload or a switch, for the quiz the
 * state holds and its questions only. A draft for a graded quiz is a retake
 * in progress, so the results are cleared first, as the quiz's Retake does.
 * Returns the same state when the draft does not apply or changes nothing.
 */
export const applyDraftAnswers = (
  state: LearningState,
  draft: DraftAnswers,
): LearningState => {
  const { quiz } = state;
  if (!quiz || quiz.id !== draft.quizId) {
    return state;
  }

  const answers = Object.fromEntries(
    quiz.questions.flatMap(({ id, options }) => {
      const answer = draft.answers[id];
      return answer !== undefined && answer < options.length
        ? [[id, answer]]
        : [];
    }),
  );
  if (!quiz.submitted && isSameAnswers(answers, quiz.answers)) {
    return state;
  }

  const base = quiz.submitted ? retakeQuiz(state) : state;
  return { ...base, quiz: { ...quiz, answers, submitted: false } };
};
