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

/** Longest part of the student's first message the title is summarised from. */
export const TITLE_INPUT_MAX_CHARS = 1000;

/** How long the title may take; after it the conversation keeps its first message, cut, as a title. */
export const TITLE_TIMEOUT_MS = 15_000;

/** Upper bound on what is remembered about the student in the Supervisor's prompt (E4). */
export const MEMORY_PROMPT_MAX_CHARS = 1200;

/** Concepts the student found hard, at most, in the prompt; weakest first. */
export const MEMORY_PROMPT_MAX_CONCEPTS = 5;

/** Topics studied before, at most, in the prompt; most recent first. */
export const MEMORY_PROMPT_MAX_TOPICS = 5;

/** Concepts the student found hard, at most, that the Quiz Agent revisits. */
export const QUIZ_WEAK_CONCEPTS = 3;

/** Headings of what the Supervisor reads besides the app context and state. */
export const STUDENT_MEMORY_HEADING = "## What you remember about this student";
export const CONVERSATION_SUMMARY_HEADING = "## Earlier in this conversation";
