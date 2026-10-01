import { z } from "zod";

import { TITLE_MAX_LENGTH } from "../constants/conversations";
import { ScoreSchema, StageSchema } from "./learning-state";

/** What the database keeps; `abandoned` is worked out when a row is read. */
export const STORED_CONVERSATION_STATUSES = ["active", "completed"] as const;
export const CONVERSATION_STATUSES = [
  ...STORED_CONVERSATION_STATUSES,
  "abandoned",
] as const;
export const ATTEMPT_STATUSES = ["in_progress", "submitted"] as const;

export const ConversationStatusSchema = z.enum(CONVERSATION_STATUSES);
export const AttemptStatusSchema = z.enum(ATTEMPT_STATUSES);

/** A conversation as the sidebar lists it. */
export const ConversationSummarySchema = z.object({
  id: z.uuid(),
  /** `null` until the first message. */
  title: z.string().nullable(),
  topic: z.string().nullable(),
  stage: StageSchema,
  status: ConversationStatusSchema,
  /** The latest graded attempt's score. */
  score: ScoreSchema.nullable(),
  lastActivityAt: z.iso.datetime({ offset: true }),
  createdAt: z.iso.datetime({ offset: true }),
});

export const ConversationListSchema = z.object({
  conversations: z.array(ConversationSummarySchema),
});

/** `PATCH /api/conversations/[id]`. */
export const RenameConversationSchema = z.object({
  title: z.string().trim().min(1).max(TITLE_MAX_LENGTH),
});

/** One quiz attempt as the history lists it. Never the answer key. */
export const QuizAttemptSummarySchema = z.object({
  id: z.uuid(),
  attemptNo: z.int().min(1),
  status: AttemptStatusSchema,
  questionCount: z.int().min(0),
  answeredCount: z.int().min(0),
  score: ScoreSchema.nullable(),
  startedAt: z.iso.datetime({ offset: true }),
  submittedAt: z.iso.datetime({ offset: true }).nullable(),
});

export type StoredConversationStatus =
  (typeof STORED_CONVERSATION_STATUSES)[number];
export type ConversationStatus = z.infer<typeof ConversationStatusSchema>;
export type AttemptStatus = z.infer<typeof AttemptStatusSchema>;
export type ConversationSummary = z.infer<typeof ConversationSummarySchema>;
export type RenameConversation = z.infer<typeof RenameConversationSchema>;
export type QuizAttemptSummary = z.infer<typeof QuizAttemptSummarySchema>;
