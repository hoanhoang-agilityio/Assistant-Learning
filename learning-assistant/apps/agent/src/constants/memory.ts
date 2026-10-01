/**
 * Rough characters per token, to estimate a thread's size without a
 * tokenizer. Only the summary's trigger depends on it.
 */
export const CHARS_PER_TOKEN = 4;

/**
 * Once the messages after the summary pass this many tokens, the older
 * ones are folded into it after the turn (E1b).
 */
export const SUMMARY_TRIGGER_TOKENS = 3000;

/** Turns that always stay verbatim: the current one and the ones before it. */
export const SUMMARY_KEEP_TURNS = 3;

/** Longest text of one message the summariser reads; a tool's output is mostly on the canvas. */
export const SUMMARY_ITEM_MAX_CHARS = 600;

/** Ends a message the summariser reads cut short. */
export const TRUNCATION_MARK = "…";

/** Heading of the summary in what the Supervisor reads. */
export const CONVERSATION_SUMMARY_HEADING = "## Earlier in this conversation";
