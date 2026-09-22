import {
  QUESTION_COUNT,
  type Settings,
  SettingsSchema,
} from "@repo/shared/schemas";

import { DEFAULT_SETTINGS } from "@/constants/settings";

/**
 * Reads persisted settings. Each field that is missing or invalid falls back
 * to its default, so one bad field does not reset the rest.
 */
export const parseSettings = (raw: unknown): Settings => {
  const input = raw && typeof raw === "object" ? raw : {};
  const shape = SettingsSchema.shape;
  const pick = <K extends keyof Settings>(key: K): Settings[K] => {
    const parsed = shape[key].safeParse(
      (input as Record<string, unknown>)[key],
    );
    return parsed.success
      ? (parsed.data as Settings[K])
      : DEFAULT_SETTINGS[key];
  };

  return {
    questionCount: pick("questionCount"),
    learningLevel: pick("learningLevel"),
    theme: pick("theme"),
  };
};

export const clampQuestionCount = (count: number): number => {
  if (!Number.isFinite(count)) {
    return QUESTION_COUNT.default;
  }
  return Math.min(
    QUESTION_COUNT.max,
    Math.max(QUESTION_COUNT.min, Math.round(count)),
  );
};
