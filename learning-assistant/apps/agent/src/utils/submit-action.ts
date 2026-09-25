import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import {
  type QuizSubmission,
  QuizSubmissionSchema,
} from "@repo/shared/schemas";
import { z } from "zod";

/** The part of `forwardedProps` the A2UI renderer fills on a surface action. */
const ForwardedActionSchema = z.object({
  a2uiAction: z.object({
    userAction: z.object({
      name: z.string(),
      context: z.unknown().optional(),
    }),
  }),
});

/**
 * Reads a Submit press from `forwardedProps.a2uiAction`. Returns `null` for
 * any other run. A Submit whose context cannot be read still counts as a
 * Submit, with `submission` left out, so grading falls back to the answers
 * in state and explains what is missing.
 */
export const parseSubmitAction = (
  forwardedProps: unknown,
): { submission?: QuizSubmission } | null => {
  const parsed = ForwardedActionSchema.safeParse(forwardedProps);
  if (!parsed.success) {
    return null;
  }

  const { name, context } = parsed.data.a2uiAction.userAction;
  if (name !== QUIZ_ACTIONS.submit) {
    return null;
  }

  const submission = QuizSubmissionSchema.safeParse(context);
  return submission.success ? { submission: submission.data } : {};
};
