import type { OnActionCallback } from "@copilotkit/a2ui-renderer";

import { FeedbackSummary } from "@/features/canvas/components/FeedbackSummary";
import { FeedbackSurface } from "@/features/canvas/components/FeedbackSurface";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

export interface FeedbackStageViewProps {
  operations: readonly A2UIMessage[];
  /** Changes only with the operations; remounts the surface for new ones. */
  surfaceKey: string;
  summary: string;
  hasSurface: boolean;
  onAction: OnActionCallback;
}

/** The Evaluator's surface, or its plain summary. */
export const FeedbackStageView = ({
  operations,
  surfaceKey,
  summary,
  hasSurface,
  onAction,
}: FeedbackStageViewProps) =>
  hasSurface ? (
    <FeedbackSurface
      key={surfaceKey}
      operations={operations}
      summary={summary}
      onAction={onAction}
    />
  ) : (
    <FeedbackSummary summary={summary} />
  );
