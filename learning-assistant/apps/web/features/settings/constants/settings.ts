/** The settings API. The settings store and the route handler share it. */
export const SETTINGS_API_PATH = "/api/settings";

/** How long a settings change waits for the next one before it is saved. */
export const SETTINGS_SAVE_DELAY_MS = 500;

export const INVALID_SETTINGS_STATUS = 400;
export const INVALID_SETTINGS_ERROR = "Those settings are not valid.";
