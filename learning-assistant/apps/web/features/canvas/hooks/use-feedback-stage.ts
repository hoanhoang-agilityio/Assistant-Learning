import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import { FEEDBACK_ACTIONS } from "@repo/shared/a2ui/feedback-catalog";
import type { Feedback } from "@repo/shared/schemas";
import { useMemo } from "react";

import {
  parseFeedbackOperations,
  parseReviewConcept,
} from "@/features/canvas/utils/feedback";
import { useRequestStage } from "@/hooks/use-stage-request-store";

/**
 * The Feedback surface's operations and actions. `surfaceKey` changes only
 * when the operations do, so the surface is redrawn once per new feedback
 * (the agent's state is re-read, as new objects, on every render);
 * `feedbackKey` changes with any new feedback. A review link opens the notes.
 */
export const useFeedbackStage = (feedback: Feedback) => {
  const requestStage = useRequestStage();
  const surfaceKey = JSON.stringify(feedback.a2uiOperations);
  const operations = useMemo(
    () => parseFeedbackOperations(JSON.parse(surfaceKey) as unknown[]),
    [surfaceKey],
  );

  const handleAction = (message: A2UIClientEventMessage) => {
    const action = message.userAction;
    if (action?.name !== FEEDBACK_ACTIONS.reviewConcept) {
      return;
    }
    if (parseReviewConcept(action.context)) {
      return requestStage("notes");
    }
  };

  return {
    operations,
    surfaceKey,
    feedbackKey: `${surfaceKey}${feedback.summary}`,
    summary: feedback.summary,
    hasSurface: operations.length > 0,
    handleAction,
  };
};
