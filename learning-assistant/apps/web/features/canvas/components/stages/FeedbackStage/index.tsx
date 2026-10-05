import type { Feedback } from "@repo/shared/schemas";

import { FeedbackStageView } from "@/features/canvas/components/stages/FeedbackStageView";
import { useFeedbackStage } from "@/features/canvas/hooks/use-feedback-stage";

export interface FeedbackStageProps {
  feedback: Feedback;
}

/** The Feedback stage: the dynamic surface from state. */
export const FeedbackStage = ({ feedback }: FeedbackStageProps) => {
  const { operations, surfaceKey, summary, hasSurface, handleAction } =
    useFeedbackStage(feedback);

  return (
    <FeedbackStageView
      operations={operations}
      surfaceKey={surfaceKey}
      summary={summary}
      hasSurface={hasSurface}
      onAction={handleAction}
    />
  );
};
