import { z } from "zod";

import { EvaluationSchema, ScoreSchema } from "./learning-state";

/** One graded attempt as the History page plots it. */
export const GradedAttemptSchema = z.object({
  attemptNo: z.int().min(1),
  score: ScoreSchema,
  submittedAt: z.iso.datetime({ offset: true }),
});

/** A conversation's quiz history: one topic, its scores over time. */
export const TopicHistorySchema = z.object({
  conversationId: z.uuid(),
  /** The conversation's title, else its research topic; `null` for neither. */
  title: z.string().nullable(),
  /** Oldest first; at least one. */
  attempts: z.array(GradedAttemptSchema).min(1),
  /** Per-concept mastery in the latest graded attempt. */
  mastery: EvaluationSchema.shape.mastery,
});

/** Every topic with a graded quiz, the most recently graded first. */
export const LearningHistorySchema = z.object({
  topics: z.array(TopicHistorySchema),
});

export type GradedAttempt = z.infer<typeof GradedAttemptSchema>;
export type TopicHistory = z.infer<typeof TopicHistorySchema>;
export type LearningHistory = z.infer<typeof LearningHistorySchema>;
