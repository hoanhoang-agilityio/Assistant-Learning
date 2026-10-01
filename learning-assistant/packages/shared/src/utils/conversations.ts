import {
  ABANDONED_AFTER_MS,
  AUTO_TITLE_MAX_LENGTH,
  COMPLETED_STAGES,
  TITLE_ELLIPSIS,
} from "../constants/conversations";
import type {
  ConversationStatus,
  Stage,
  StoredConversationStatus,
} from "../schemas";

/** Graded and given feedback: completed. Anything earlier, a retake included: active. */
export const getStoredStatus = (stage: Stage): StoredConversationStatus =>
  COMPLETED_STAGES.includes(stage) ? "completed" : "active";

/** An active conversation left alone for a week reads as abandoned; nothing stores that. */
export const getConversationStatus = (
  stored: StoredConversationStatus,
  lastActivityAt: Date,
  now: Date,
): ConversationStatus =>
  stored === "active" &&
  now.getTime() - lastActivityAt.getTime() > ABANDONED_AFTER_MS
    ? "abandoned"
    : stored;

/**
 * A title from the student's first message: one line, cut at a word near
 * `AUTO_TITLE_MAX_LENGTH`. `null` when the message has no text.
 */
export const createAutoTitle = (message: string): string | null => {
  const line = message.replace(/\s+/g, " ").trim();
  if (!line) {
    return null;
  }
  if (line.length <= AUTO_TITLE_MAX_LENGTH) {
    return line;
  }

  const cut = line.slice(0, AUTO_TITLE_MAX_LENGTH - TITLE_ELLIPSIS.length);
  const lastSpace = cut.lastIndexOf(" ");
  const words = lastSpace > cut.length / 2 ? cut.slice(0, lastSpace) : cut;
  return `${words.trimEnd()}${TITLE_ELLIPSIS}`;
};
