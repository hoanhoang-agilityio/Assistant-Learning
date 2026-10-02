/** The assistant (chat + canvas). Needs a saved OpenAI API key. */
export const HOME_ROUTE = "/";

/** Where the user enters their OpenAI API key before using the assistant. */
export const API_KEY_ROUTE = "/api-key";

/** What the assistant keeps about the user (the Memory panel, from Settings). */
export const MEMORY_ROUTE = "/memory";

/** Scores over time per topic, per-concept mastery, and Retake. */
export const HISTORY_ROUTE = "/history";

/**
 * `/?retake=<conversation id>`: open that conversation and retake its
 * graded quiz (the History page's Retake).
 */
export const RETAKE_SEARCH_PARAM = "retake";
