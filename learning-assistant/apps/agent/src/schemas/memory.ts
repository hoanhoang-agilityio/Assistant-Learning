import { LearningLevelSchema } from "@repo/shared/schemas";
import { z } from "zod";

/** The summariser's output: the conversation's older messages, folded. */
export const ConversationSummarySchema = z.object({
  summary: z.string().min(1),
});

/** The title a conversation gets from the student's first message. */
export const ConversationTitleSchema = z.object({
  title: z.string().min(1),
});

/**
 * What one message says about the student as a learner; `null` for each
 * field it says nothing new about.
 */
export const ProfileObservationSchema = z.object({
  level: LearningLevelSchema.nullable(),
  style: z.string().nullable(),
  language: z.string().nullable(),
});

export type ProfileObservation = z.infer<typeof ProfileObservationSchema>;
