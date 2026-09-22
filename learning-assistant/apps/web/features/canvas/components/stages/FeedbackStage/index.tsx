import type { Feedback, Reflection } from "@repo/shared/schemas";

import { FeedbackStageView } from "@/features/canvas/components/stages/FeedbackStageView";
import { useFeedbackStage } from "@/features/canvas/hooks/use-feedback-stage";

export interface FeedbackStageProps {
  feedback: Feedback;
  reflection: Reflection | null;
}

/** The Feedback stage: the dynamic surface from state and the reflection form. */
export const FeedbackStage = ({ feedback, reflection }: FeedbackStageProps) => {
  const {
    operations,
    surfaceKey,
    feedbackKey,
    summary,
    hasSurface,
    handleAction,
  } = useFeedbackStage(feedback);

  return (
    <FeedbackStageView
      operations={operations}
      surfaceKey={surfaceKey}
      feedbackKey={feedbackKey}
      summary={summary}
      hasSurface={hasSurface}
      reflection={reflection}
      onAction={handleAction}
    />
  );
};
