import {
  FEEDBACK_ACTIONS,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { z } from "zod";

import type { A2UIMessage } from "@/features/canvas/types/a2ui";
import { parseSurfaceOperations } from "@/features/canvas/utils/a2ui-operations";

const ReviewConceptSchema = z.object({ concept: z.string().min(1) });

/** The `review_concept` action a ReviewLink dispatches. */
export const createReviewConceptAction = (concept: string) => ({
  event: { name: FEEDBACK_ACTIONS.reviewConcept, context: { concept } },
});

export const parseReviewConcept = (context: unknown): string | null => {
  const parsed = ReviewConceptSchema.safeParse(context);
  return parsed.success ? parsed.data.concept : null;
};

/**
 * The operations from `feedback.a2uiOperations` that draw the Feedback
 * surface. Empty (show the plain summary) unless they start by creating it
 * and every one of them targets it.
 */
export const parseFeedbackOperations = (
  operations: readonly unknown[],
): A2UIMessage[] => parseSurfaceOperations(operations, FEEDBACK_SURFACE_ID);
