import { z } from "zod";

export const LEARNING_LEVELS = [
  "beginner",
  "intermediate",
  "advanced",
] as const;
/** `system` follows the device's light/dark preference. */
export const THEMES = ["system", "light", "dark"] as const;

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

/** Arguments of the `setLearningSettings` frontend tool. Send only what changes. */
export const SetLearningSettingsParamsSchema = z
  .object({
    questionCount: SettingsSchema.shape.questionCount
      .optional()
      .describe(
        `questions per quiz, ${QUESTION_COUNT.min} to ${QUESTION_COUNT.max}`,
      ),
    learningLevel: LearningLevelSchema.optional().describe(
      "how deep the research, learning material and quiz go",
    ),
  })
  .refine(
    (params) =>
      params.questionCount !== undefined || params.learningLevel !== undefined,
    { message: "Send questionCount, learningLevel or both" },
  );

export type LearningLevel = z.infer<typeof LearningLevelSchema>;
export type Theme = z.infer<typeof ThemeSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type SetLearningSettingsParams = z.infer<
  typeof SetLearningSettingsParamsSchema
>;
