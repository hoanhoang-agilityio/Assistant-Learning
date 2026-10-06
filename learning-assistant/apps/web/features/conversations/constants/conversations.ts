import { TITLE_MAX_LENGTH } from "@repo/shared/constants/conversations";
import type { ConversationStatus, Stage } from "@repo/shared/schemas";

/** The conversations API. The sidebar and the route handlers share it. */
export const CONVERSATIONS_API_PATH = "/api/conversations";

/** `/api/conversations/[id]/answers`: the quiz's draft answers. */
export const CONVERSATION_ANSWERS_SEGMENT = "answers";

/** `/api/conversations/[id]/title`: a title summarised from the first message. */
export const CONVERSATION_TITLE_SEGMENT = "title";

/** Pause after the last pick before the draft answers are kept. */
export const DRAFT_ANSWERS_SAVE_DELAY_MS = 800;

export const CONVERSATION_NOT_FOUND_STATUS = 404;
export const CONVERSATION_NOT_FOUND_ERROR = "Conversation not found.";

export const BAD_REQUEST_STATUS = 400;
export const INVALID_TITLE_ERROR = `A title needs 1 to ${TITLE_MAX_LENGTH} characters.`;
export const INVALID_TITLE_MESSAGE_ERROR =
  "Send { message } with the first message.";
export const MISSING_API_KEY_STATUS = 401;
export const MISSING_API_KEY_ERROR =
  "Add your OpenAI API key to name the conversation.";
export const TITLE_FAILED_STATUS = 502;
export const TITLE_FAILED_ERROR = "The conversation could not be named.";
export const INVALID_ANSWERS_ERROR =
  "Send { quizId, answers } with an option index per question id.";
export const CREATED_STATUS = 201;
export const NO_CONTENT_STATUS = 204;

/** `localStorage` key for the open conversation and the sidebar's state. */
export const CONVERSATIONS_STORAGE_KEY = "learning-assistant:conversations";

/** A conversation the student has not written in yet. */
export const UNTITLED_TITLE = "New topic";

export const STAGE_LABELS: Record<Stage, string> = {
  idle: "Not started",
  research: "Research",
  material: "Learning Material",
  quiz: "Quiz",
  evaluation: "Evaluation",
  score: "Score",
  feedback: "Feedback",
};

export const STATUS_LABELS: Record<ConversationStatus, string> = {
  active: "Active",
  completed: "Completed",
  abandoned: "Abandoned",
};

export const CONVERSATION_COPY = {
  heading: "Conversations",
  newTopic: "New topic",
  search: "Search conversations",
  noMatches: "No conversations match.",
  rename: "Rename",
  delete: "Delete",
  cancel: "Cancel",
  save: "Save",
  deleteConfirm: "Delete for good? Its chat, canvas and quiz attempts go too.",
  collapse: "Hide conversations",
  expand: "Show conversations",
  loadFailed: "Your conversations could not be loaded.",
  retry: "Try again",
  actionFailed: "That did not work. Try again.",
  resumeDismiss: "Dismiss",
} as const;

/** DOM id of the open conversation list, for its toggles' `aria-controls`. */
export const CONVERSATION_SIDEBAR_ID = "conversation-sidebar";

/** The sidebar's and the rail's icon buttons. */
export const CONVERSATION_ICON_BUTTON_CLASS =
  "rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-slate-700 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200";
