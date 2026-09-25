import { A2UIProvider } from "@copilotkit/a2ui-renderer";
import { FEEDBACK_SURFACE_ID } from "@repo/shared/a2ui/feedback-catalog";
import type { Feedback } from "@repo/shared/schemas";

import { FeedbackSummary } from "@/features/canvas/components/FeedbackSummary";
import { SurfaceDraftBody } from "@/features/canvas/components/SurfaceDraftBody";
import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import { FEEDBACK_UI_CATALOG } from "@/features/canvas/constants/feedback-catalog";

export interface FeedbackDraftProps {
  feedback: Feedback;
}

/**
 * The feedback being written: the Evaluator's surface as it grows, else its
 * summary so far, as the finished stage would show them.
 */
export const FeedbackDraft = ({ feedback }: FeedbackDraftProps) => {
  const summary = feedback.summary ? (
    <FeedbackSummary summary={feedback.summary} />
  ) : (
    <div
      className={`${CARD_CLASS} h-40 animate-pulse bg-slate-100 dark:bg-slate-900/60`}
    />
  );

  return feedback.a2uiOperations.length > 0 ? (
    <A2UIProvider catalog={FEEDBACK_UI_CATALOG}>
      <SurfaceDraftBody
        surfaceId={FEEDBACK_SURFACE_ID}
        operations={feedback.a2uiOperations}
        fallback={summary}
      />
    </A2UIProvider>
  ) : (
    summary
  );
};
