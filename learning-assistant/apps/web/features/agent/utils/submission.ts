import type { LearningState, QuizSubmission } from "@repo/shared/schemas";

import { TOOL_ERRORS } from "@/features/agent/constants/tools";
import type { SubmissionCheck } from "@/features/agent/types/submission";

/** A quiz with unanswered questions cannot be graded. */
const formatQuizIncompleteError = (answered: number, total: number) =>
  `Only ${answered} of ${total} questions are answered. The student must answer every question on the canvas first.`;

/**
 * Whether the quiz in `state` can be graded. The answers come from the Submit
 * action when there is one (`submission`), otherwise from `quiz.answers`, and
 * are limited to this quiz's questions.
 */
export const validateSubmission = (
  state: LearningState,
  submission?: QuizSubmission,
): SubmissionCheck => {
  const { quiz } = state;
  if (!quiz) return { ok: false, error: TOOL_ERRORS.noQuiz };
  if (quiz.submitted) {
    return { ok: false, error: TOOL_ERRORS.quizAlreadySubmitted };
  }
  if (submission && submission.quizId !== quiz.id) {
    return { ok: false, error: TOOL_ERRORS.staleQuiz };
  }

  const given = submission?.answers ?? quiz.answers;
  const answers = Object.fromEntries(
    quiz.questions.flatMap(({ id }) => {
      const answer = given[id];
      return answer === undefined ? [] : [[id, answer]];
    }),
  );
  const answered = Object.keys(answers).length;
  if (answered < quiz.questions.length) {
    return {
      ok: false,
      error: formatQuizIncompleteError(answered, quiz.questions.length),
    };
  }

  return { ok: true, quiz, answers };
};
