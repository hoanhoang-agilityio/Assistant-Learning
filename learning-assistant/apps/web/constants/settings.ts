import { QUESTION_COUNT, type Settings } from "@repo/shared/schemas";

import { DEFAULT_PROVIDER, PROVIDER_CATALOG } from "@/constants/models";

export const DEFAULT_SETTINGS: Settings = {
  provider: DEFAULT_PROVIDER,
  model: PROVIDER_CATALOG[DEFAULT_PROVIDER].models[0].id,
  reasoningEffort: "low",
  questionCount: QUESTION_COUNT.default,
  learningLevel: "beginner",
  theme: "light",
};

/** `localStorage` key for the persisted settings store. */
export const SETTINGS_STORAGE_KEY = "learning-assistant:settings";
