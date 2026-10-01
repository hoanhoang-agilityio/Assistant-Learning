import { z } from "zod";

import {
  PROFILE_LANGUAGE_MAX_LENGTH,
  PROFILE_STYLE_MAX_LENGTH,
} from "../constants/memory";
import { LearningLevelSchema } from "./settings";

export const PROFILE_FIELDS = ["level", "style", "language"] as const;

export const ProfileFieldSchema = z.enum(PROFILE_FIELDS);

const StyleSchema = z.string().trim().min(1).max(PROFILE_STYLE_MAX_LENGTH);
const LanguageSchema = z
  .string()
  .trim()
  .min(1)
  .max(PROFILE_LANGUAGE_MAX_LENGTH);

/**
 * What the student is like as a learner, kept across conversations. Each
 * field is `null` until a run notices it or the student sets it.
 */
export const LearnerProfileSchema = z.object({
  /** The level they ask for or show; the settings still decide what tools write. */
  level: LearningLevelSchema.nullable(),
  /** How they like explanations, in a few words. */
  style: StyleSchema.nullable(),
  /** The language they want answers in. */
  language: LanguageSchema.nullable(),
});

/** A concept's running mastery over every graded attempt that tested it. */
export const ConceptMemorySchema = z.object({
  /** The concept's name, normalised: what it is stored and deleted by. */
  key: z.string().min(1),
  /** The name as a quiz last wrote it. */
  concept: z.string().min(1),
  correct: z.int().min(0),
  total: z.int().min(1),
  percent: z.number().min(0).max(100),
  updatedAt: z.iso.datetime({ offset: true }),
});

/** A topic the student was quizzed on: one per conversation. */
export const TopicMemorySchema = z.object({
  conversationId: z.uuid(),
  topic: z.string().min(1),
  bestPercent: z.number().min(0).max(100),
  latestPercent: z.number().min(0).max(100),
  attempts: z.int().min(1),
  updatedAt: z.iso.datetime({ offset: true }),
});

/** Everything kept about one student, as `GET /api/memory` returns it. */
export const StudentMemorySchema = z.object({
  profile: LearnerProfileSchema,
  /** Weakest first. */
  concepts: z.array(ConceptMemorySchema),
  /** Most recent first. */
  topics: z.array(TopicMemorySchema),
});

/**
 * `PATCH /api/memory` and what a run learns: only the fields given change,
 * and `null` forgets one.
 */
export const ProfileUpdateSchema = z
  .object({
    level: LearningLevelSchema.nullable().optional(),
    style: StyleSchema.nullable().optional(),
    language: LanguageSchema.nullable().optional(),
  })
  .refine((update) => PROFILE_FIELDS.some((field) => field in update), {
    message: "Send level, style or language",
  });

export type ProfileField = z.infer<typeof ProfileFieldSchema>;
export type LearnerProfile = z.infer<typeof LearnerProfileSchema>;
export type ConceptMemory = z.infer<typeof ConceptMemorySchema>;
export type TopicMemory = z.infer<typeof TopicMemorySchema>;
export type StudentMemory = z.infer<typeof StudentMemorySchema>;
export type ProfileUpdate = z.infer<typeof ProfileUpdateSchema>;
