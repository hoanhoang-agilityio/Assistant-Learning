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

/** Frontend tool: changes the quiz question count and the learning level. */
export const SET_LEARNING_SETTINGS_TOOL = "setLearningSettings";

/**
 * Frontend tools with no handler: the chat draws a fixed card from the
 * arguments. They only render UI, so they are registered with `useComponent`,
 * and the Supervisor picks the card that fits the question.
 */
export const CHAT_CARD_TOOLS = {
  concept: "showConceptCard",
  comparison: "showComparison",
  steps: "showSteps",
  codeExample: "showCodeExample",
} as const;

/**
 * Server tool: the Supervisor composes a free-form A2UI surface and picks
 * where it goes: the chat (chat catalog) or the canvas Board (board catalog).
 */
export const RENDER_SURFACE_TOOL = "renderSurface";

/** Server tool: returns a Board view's components so they can be edited. */
export const READ_BOARD_SURFACE_TOOL = "readBoardSurface";

/** Server tool: replaces a Board view's components, keeping its id. */
export const UPDATE_BOARD_SURFACE_TOOL = "updateBoardSurface";

/** Server tool: removes Board views; the chat, not the Board, says so. */
export const DELETE_BOARD_SURFACE_TOOL = "deleteBoardSurface";
