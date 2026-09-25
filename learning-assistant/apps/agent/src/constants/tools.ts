import {
  CHAT_CARD_TOOLS,
  CONFIRM_NEW_TOPIC_TOOL,
  DELETE_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  SET_LAYOUT_TOOL,
  SET_LEARNING_SETTINGS_TOOL,
  SET_THEME_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import type { SubagentTool } from "@repo/shared/schemas";

/** What the Supervisor LLM reads about each subagent tool. */
export const TOOL_DESCRIPTIONS: Record<SubagentTool, string> = {
  research:
    "Research a topic for the student and show the reading, key insight, flashcards and sources on the canvas.",
  makeMaterial:
    "Turn the current research into editable markdown learning material on the canvas. Needs research.",
  simplify:
    'Rewrite the learning material in student-friendly language. scope "all" rewrites the whole set into the Simplified view; scope "selection" rewrites only `selection`, which must be copied exactly from the learning material. Needs learning material.',
  generateQuiz:
    "Write a new multiple-choice quiz from the learning material the student is viewing, replacing any current quiz and its results. Needs learning material.",
  evaluate:
    "Grade the quiz with the answers the student picked on the canvas. Only when they ask in chat to grade it; the Submit button grades it without you. Needs every question answered.",
};

/**
 * Tool failures the Supervisor explains to the student. A missing
 * prerequisite says what to do first.
 */
export const TOOL_ERRORS = {
  noResearch:
    "There is no research yet, so learning material cannot be made. Research a topic first.",
  noMaterial:
    "There is no learning material yet, so there is nothing to simplify. Make learning material first.",
  noSelection:
    'Simplifying a selection needs the selected text. Pass it in "selection", or use scope "all".',
  selectionNotFound:
    "The selected text was not found in the learning material. It must be copied exactly from the learning material the student is viewing.",
  noMaterialForQuiz:
    "There is no learning material yet, so there is nothing to quiz on. Make learning material first.",
  noQuiz: "There is no quiz yet. Write a quiz first.",
  quizAlreadySubmitted:
    "This quiz was already graded. The student can Retake it or ask for new questions.",
  staleQuiz:
    "The answers were for a quiz that has since been replaced. The student should answer the current quiz.",
  stopped: "The student stopped this step.",
} as const;

/** Prefix for an unexpected failure, followed by the error message. */
export const TOOL_FAILURE_PREFIX: Record<SubagentTool, string> = {
  research: "Research failed",
  makeMaterial: "Making learning material failed",
  simplify: "Simplifying the learning material failed",
  generateQuiz: "Writing the quiz failed",
  evaluate: "Evaluating the quiz failed",
};

/** What the Supervisor LLM reads about `renderSurface`. */
export const RENDER_SURFACE_TOOL_DESCRIPTION =
  "Compose a custom view from components and draw it in the chat or on the " +
  'canvas Board. target "chat": a compact card built from Panel (id "root"), ' +
  "Section, Paragraph, BulletList, Callout, Table, Timeline, Meter and " +
  'TagList. target "canvas": a wide view on the Board that stays; it may also ' +
  "use Stack (the usual root), Columns, ArticleCard, InsightCallout, " +
  "Flashcards, StatTiles, CodeBlock, KeyValueList, ProsCons and Checklist. " +
  "Do not repeat its content in text.";

/** What the Supervisor LLM reads about `readBoardSurface`. */
export const READ_BOARD_SURFACE_TOOL_DESCRIPTION =
  "Get a Board view's title and components, to edit it with " +
  "updateBoardSurface. Nothing is shown to the student.";

/** What the Supervisor LLM reads about `updateBoardSurface`. */
export const UPDATE_BOARD_SURFACE_TOOL_DESCRIPTION =
  "Replace a Board view's components with a revised list, keeping its id; " +
  "it moves to the top of the Board. Send the whole list (read it first " +
  "with readBoardSurface), " +
  "with the Board components renderSurface allows for the canvas. Use it " +
  "only when the student asks to change a view that is already there, " +
  "never to turn a view into one about a different subject; a new view is " +
  "renderSurface.";

/** What the Supervisor LLM reads about `deleteBoardSurface`. */
export const DELETE_BOARD_SURFACE_TOOL_DESCRIPTION =
  "Remove whole views from the Board: pass their ids, or every id to clear " +
  "it. Confirm in chat afterwards; never draw a view to announce it. To " +
  "remove part of a view, use updateBoardSurface instead.";

/** `deleteBoardSurface` was called with no ids. */
export const NO_SURFACE_IDS =
  "No Board view ids were given. Pass the ids to remove.";

/** Starts the result of an invalid surface, followed by the errors. */
export const SURFACE_ERROR_PREFIX =
  "The surface was not drawn. Fix these errors and call the tool again:";

/** A read or update named a Board view that does not exist; the ids follow. */
export const BOARD_SURFACE_NOT_FOUND =
  "There is no Board view with that id. The Board has:";

/** A read or update while the Board is empty. */
export const BOARD_EMPTY =
  "The Board is empty. Use renderSurface with target canvas to make a view.";

/**
 * Tools whose chat card says what happened. After one succeeds the Supervisor
 * writes nothing; `muteRepliesAfterCards` drops any reply it writes anyway.
 * `readBoardSurface` has no card, so it is not here.
 */
export const CARD_TOOLS: ReadonlySet<string> = new Set([
  ...Object.keys(TOOL_DESCRIPTIONS),
  ...Object.values(CHAT_CARD_TOOLS),
  CONFIRM_NEW_TOPIC_TOOL,
  SET_THEME_TOOL,
  SET_LAYOUT_TOOL,
  SET_LEARNING_SETTINGS_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
  DELETE_BOARD_SURFACE_TOOL,
]);
