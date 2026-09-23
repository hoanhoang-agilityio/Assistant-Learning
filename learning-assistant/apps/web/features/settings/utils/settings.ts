import {
  QUESTION_COUNT,
  type Settings,
  SettingsSchema,
} from "@repo/shared/schemas";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import type { ResolvedTheme } from "@/features/settings/types/settings";

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

/** `system` becomes the device's preference; light and dark stay as they are. */
export const resolveTheme = (
  theme: Settings["theme"],
  prefersDark: boolean,
): ResolvedTheme => {
  if (theme === "system") {
    return prefersDark ? "dark" : "light";
  }
  return theme;
};

/** The `setTheme` tool result: what the student now sees. */
export const describeTheme = (
  theme: Settings["theme"],
  prefersDark: boolean,
): string => {
  const onScreen = resolveTheme(theme, prefersDark);
  if (theme === "system") {
    return `Theme set to system: it follows the device, which is ${onScreen} right now.`;
  }
  return `Theme set to ${onScreen}.`;
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
