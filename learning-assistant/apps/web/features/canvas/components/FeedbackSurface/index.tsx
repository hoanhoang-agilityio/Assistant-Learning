import { A2UIProvider, type OnActionCallback } from "@copilotkit/a2ui-renderer";

import { FeedbackSurfaceBody } from "@/features/canvas/components/FeedbackSurfaceBody";
import { FEEDBACK_UI_CATALOG } from "@/features/canvas/constants/feedback-catalog";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

export interface FeedbackSurfaceProps {
  operations: readonly A2UIMessage[];
  summary: string;
  onAction?: OnActionCallback;
}

/** The dynamic Feedback surface, drawn with the Feedback catalog. */
export const FeedbackSurface = ({
  operations,
  summary,
  onAction,
}: FeedbackSurfaceProps) => (
  <A2UIProvider catalog={FEEDBACK_UI_CATALOG} onAction={onAction}>
    <FeedbackSurfaceBody operations={operations} summary={summary} />
  </A2UIProvider>
);
