import { QUESTION_COUNT, type Settings } from "@repo/shared/schemas";

export const DEFAULT_SETTINGS: Settings = {
  questionCount: QUESTION_COUNT.default,
  learningLevel: "beginner",
  theme: "system",
};

/** Matches when the device prefers a dark theme. */
export const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/** Class on <html> that turns on the `dark:` variant. */
export const DARK_THEME_CLASS = "dark";

export const SET_THEME_TOOL_DESCRIPTION =
  "Switch the app theme to light, dark, or system (follows the device's " +
  "light/dark preference). The result says which theme is now on screen.";

/** `localStorage` key for the persisted settings store. */
export const SETTINGS_STORAGE_KEY = "learning-assistant:settings";
