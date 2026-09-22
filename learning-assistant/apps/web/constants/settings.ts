import { QUESTION_COUNT, type Settings } from "@repo/shared/schemas";

export const DEFAULT_SETTINGS: Settings = {
  questionCount: QUESTION_COUNT.default,
  learningLevel: "beginner",
  theme: "light",
};

/** `localStorage` key for the persisted settings store. */
export const SETTINGS_STORAGE_KEY = "learning-assistant:settings";
