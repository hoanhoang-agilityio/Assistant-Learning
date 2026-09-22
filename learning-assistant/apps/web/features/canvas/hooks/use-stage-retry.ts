import type { LearningState } from "@repo/shared/schemas";

import { useSendMessage } from "@/features/canvas/hooks/use-send-message";
import { useSubmitQuiz } from "@/features/canvas/hooks/use-submit-quiz";
import { getRetryAction } from "@/features/canvas/utils/retry";

/** Retry for the task in `status.failed`, offered while the agent is idle. */
export const useStageRetry = (state: LearningState, isRunning: boolean) => {
  const sendMessage = useSendMessage();
  const submitQuiz = useSubmitQuiz();
  const action = getRetryAction(state);

  const handleRetry = () => {
    if (!action || isRunning) {
      return;
    }
    if (action.kind === "submit") {
      submitQuiz(action.action);
      return;
    }
    sendMessage(action.content);
  };

  return {
    canRetry: action !== null,
    isRetryDisabled: isRunning,
    handleRetry,
  };
};
