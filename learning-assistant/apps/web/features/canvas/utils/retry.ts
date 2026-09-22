import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import { QUIZ_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { LearningState, Quiz } from "@repo/shared/schemas";

import { RETRY_MESSAGES } from "@/features/canvas/constants/retry";
import type { RetryAction } from "@/features/canvas/types/retry";

/** The quiz Submit action, with the answers in state as its context. */
export const createSubmitAction = (quiz: Quiz): A2UIClientEventMessage => ({
  userAction: {
    name: QUIZ_ACTIONS.submit,
    surfaceId: QUIZ_TEMPLATE.surfaceId,
    context: { quizId: quiz.id, answers: quiz.answers },
  },
});

/**
 * What Retry does for the task that failed (`status.failed`), or `null` when
 * nothing failed or grading has no quiz to submit.
 */
export const getRetryAction = (state: LearningState): RetryAction | null => {
  const { failed } = state.status;
  if (!failed) {
    return null;
  }
  if (failed === "evaluate") {
    return state.quiz && !state.quiz.submitted
      ? { kind: "submit", action: createSubmitAction(state.quiz) }
      : null;
  }
  return { kind: "message", content: RETRY_MESSAGES[failed] };
};
