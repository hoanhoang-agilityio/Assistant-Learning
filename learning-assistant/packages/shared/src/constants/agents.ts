/** The agent id the runtime registers and the client connects to. */
export const LEARNING_AGENT_ID = "learning";

/**
 * The frontend tool that asks the student to confirm a new topic when learning material
 * or a quiz exist. It is human-in-the-loop: the chat renders it, and the
 * student's choice is its result.
 */
export const CONFIRM_NEW_TOPIC_TOOL = "confirmNewTopic";

/** Frontend tool: switches the theme (system, light or dark). */
export const SET_THEME_TOOL = "setTheme";

/** Frontend tool: shows, hides or pops out the chat and switches the view. */
export const SET_LAYOUT_TOOL = "setLayout";
