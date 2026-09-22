import type { OnActionCallback } from "@copilotkit/a2ui-renderer";
import type { Reflection } from "@repo/shared/schemas";

import { FeedbackSummary } from "@/features/canvas/components/FeedbackSummary";
import { FeedbackSurface } from "@/features/canvas/components/FeedbackSurface";
import { ReflectionForm } from "@/features/canvas/components/ReflectionForm";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

export interface FeedbackStageViewProps {
  operations: readonly A2UIMessage[];
  /** Changes only with the operations; remounts the surface for new ones. */
  surfaceKey: string;
  /** Changes with any new feedback; resets the reflection form. */
  feedbackKey: string;
  summary: string;
  hasSurface: boolean;
  reflection: Reflection | null;
  onAction: OnActionCallback;
}

/** The Evaluator's surface (or its plain summary), then the reflection form. */
export const FeedbackStageView = ({
  operations,
  surfaceKey,
  feedbackKey,
  summary,
  hasSurface,
  reflection,
  onAction,
}: FeedbackStageViewProps) => (
  <>
    {hasSurface ? (
      <FeedbackSurface
        key={surfaceKey}
        operations={operations}
        summary={summary}
        onAction={onAction}
      />
    ) : (
      <FeedbackSummary summary={summary} />
    )}
    <ReflectionForm key={feedbackKey} reflection={reflection} />
  </>
);
