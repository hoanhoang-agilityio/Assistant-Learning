import { z } from "zod";

export const PROVIDERS = ["openai", "anthropic", "google"] as const;
export const REASONING_EFFORTS = ["off", "low", "medium", "high"] as const;
export const LEARNING_LEVELS = [
  "beginner",
  "intermediate",
  "advanced",
] as const;
export const THEMES = ["light", "dark"] as const;

export const QUESTION_COUNT = { min: 3, max: 20, default: 5 } as const;

export const ProviderSchema = z.enum(PROVIDERS);
export const ReasoningEffortSchema = z.enum(REASONING_EFFORTS);
export const LearningLevelSchema = z.enum(LEARNING_LEVELS);
export const ThemeSchema = z.enum(THEMES);

/**
 * User settings, persisted client-side and sent to the agent in
 * `forwardedProps.settings` on every run. `model` is checked against the
 * provider's allowlist in `apps/web/constants/models.ts`, not here.
 */
export const SettingsSchema = z.object({
  provider: ProviderSchema,
  model: z.string().min(1),
  reasoningEffort: ReasoningEffortSchema,
  questionCount: z.int().min(QUESTION_COUNT.min).max(QUESTION_COUNT.max),
  learningLevel: LearningLevelSchema,
  theme: ThemeSchema,
});

export type Provider = z.infer<typeof ProviderSchema>;
export type ReasoningEffort = z.infer<typeof ReasoningEffortSchema>;
export type LearningLevel = z.infer<typeof LearningLevelSchema>;
export type Theme = z.infer<typeof ThemeSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
