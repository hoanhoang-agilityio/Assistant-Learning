import { z } from "zod";

export const LEARNING_LEVELS = [
  "beginner",
  "intermediate",
  "advanced",
] as const;
export const THEMES = ["light", "dark"] as const;

export const QUESTION_COUNT = { min: 3, max: 20, default: 5 } as const;

export const LearningLevelSchema = z.enum(LEARNING_LEVELS);
export const ThemeSchema = z.enum(THEMES);

/**
 * User settings, persisted client-side and sent to the agent in
 * `forwardedProps.settings` on every run.
 */
export const SettingsSchema = z.object({
  questionCount: z.int().min(QUESTION_COUNT.min).max(QUESTION_COUNT.max),
  learningLevel: LearningLevelSchema,
  theme: ThemeSchema,
});

export type LearningLevel = z.infer<typeof LearningLevelSchema>;
export type Theme = z.infer<typeof ThemeSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
