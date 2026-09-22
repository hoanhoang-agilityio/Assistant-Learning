import { A2UIRenderer } from "@copilotkit/a2ui-renderer";
import { FEEDBACK_SURFACE_ID } from "@repo/shared/a2ui/feedback-catalog";

import { FeedbackSummary } from "@/features/canvas/components/FeedbackSummary";
import { useFeedbackSurface } from "@/features/canvas/hooks/use-feedback-surface";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

export interface FeedbackSurfaceBodyProps {
  operations: readonly A2UIMessage[];
  /** Shown instead if the surface cannot be drawn. */
  summary: string;
}

/** Draws the Feedback surface, or the plain summary if rendering fails. */
export const FeedbackSurfaceBody = ({
  operations,
  summary,
}: FeedbackSurfaceBodyProps) => {
  const { error } = useFeedbackSurface(operations);

  return error ? (
    <FeedbackSummary summary={summary} />
  ) : (
    <A2UIRenderer surfaceId={FEEDBACK_SURFACE_ID} />
  );
};
