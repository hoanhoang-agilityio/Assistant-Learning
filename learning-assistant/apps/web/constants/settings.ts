/** Matches when the device prefers a dark theme. */
export const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/** Class on <html> that turns on the `dark:` variant. */
export const DARK_THEME_CLASS = "dark";

export const SET_THEME_TOOL_DESCRIPTION =
  "Switch the app theme to light, dark, or system (follows the device's " +
  "light/dark preference). The result says which theme is now on screen.";

/** `localStorage` key for the persisted settings store. */
export const SETTINGS_STORAGE_KEY = "learning-assistant:settings";

export const SET_LEARNING_SETTINGS_TOOL_DESCRIPTION =
  "Change the question count of the next quiz or the learning level used " +
  "for new research, learning material and quizzes. Existing content is not " +
  "regenerated. Send only what the student asked to change. The result says " +
  "which settings are now active.";

/** Chat card copy for the learning settings tool. */
export const LEARNING_SETTINGS_TOOL_COPY = {
  running: "Updating the settings",
  done: "Settings updated",
} as const;
