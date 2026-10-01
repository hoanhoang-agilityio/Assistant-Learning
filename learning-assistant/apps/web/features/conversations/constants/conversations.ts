import { TITLE_MAX_LENGTH } from "@repo/shared/constants/conversations";
import type { ConversationStatus, Stage } from "@repo/shared/schemas";

/** The conversations API. The sidebar and the route handlers share it. */
export const CONVERSATIONS_API_PATH = "/api/conversations";

export const CONVERSATION_NOT_FOUND_STATUS = 404;
export const CONVERSATION_NOT_FOUND_ERROR = "Conversation not found.";

export const BAD_REQUEST_STATUS = 400;
export const INVALID_TITLE_ERROR = `A title needs 1 to ${TITLE_MAX_LENGTH} characters.`;
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
