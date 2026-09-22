import { A2UIRenderer } from "@copilotkit/a2ui-renderer";
import { FEEDBACK_SURFACE_ID } from "@repo/shared/a2ui/feedback-catalog";

import { FeedbackSummary } from "@/features/canvas/components/FeedbackSummary";
import { SurfaceBoundary } from "@/features/canvas/components/SurfaceBoundary";
import { useFeedbackSurface } from "@/features/canvas/hooks/use-feedback-surface";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

export interface FeedbackSurfaceBodyProps {
  operations: readonly A2UIMessage[];
  /** Shown instead if the surface cannot be drawn. */
  summary: string;
}

/**
 * Draws the Feedback surface, or the plain summary if its operations are
 * rejected or a component throws while rendering.
 */
export const FeedbackSurfaceBody = ({
  operations,
  summary,
}: FeedbackSurfaceBodyProps) => {
  const { error } = useFeedbackSurface(operations);

  const fallback = <FeedbackSummary summary={summary} />;

  return error ? (
    fallback
  ) : (
    <SurfaceBoundary fallback={fallback}>
      <A2UIRenderer surfaceId={FEEDBACK_SURFACE_ID} />
    </SurfaceBoundary>
  );
};
