import {
  FEEDBACK_ACTIONS,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { REFLECTION_MESSAGE_PREFIX } from "@repo/shared/constants/messages";
import { type Reflection, ReflectionSchema } from "@repo/shared/schemas";
import { z } from "zod";

import { MAX_RATING } from "@/features/canvas/constants/feedback";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";
import type { ReflectionDraft } from "@/features/canvas/types/feedback";
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

/** A draft that can be saved: a rating from 1 to 5, the text trimmed. */
export const toReflection = ({
  rating,
  text,
}: ReflectionDraft): Reflection | null => {
  const parsed = ReflectionSchema.safeParse({ rating, text: text.trim() });
  return parsed.success ? parsed.data : null;
};

/** The chat message that shares a saved reflection with the assistant. */
export const formatReflectionMessage = ({
  rating,
  text,
}: Reflection): string =>
  text
    ? `${REFLECTION_MESSAGE_PREFIX} (${rating}/${MAX_RATING}): ${text}`
    : `${REFLECTION_MESSAGE_PREFIX}: I rated this lesson ${rating}/${MAX_RATING}.`;
