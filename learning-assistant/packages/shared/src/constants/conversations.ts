import type { Stage } from "../schemas";

/** An active conversation untouched for this long reads as abandoned. */
export const ABANDONED_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

/** Stages that mean the quiz was graded and the feedback written. */
export const COMPLETED_STAGES: readonly Stage[] = [
  "evaluation",
  "score",
  "feedback",
];

/** Longest automatic title, cut from the student's first message. */
export const AUTO_TITLE_MAX_LENGTH = 60;

/** Longest title a student may give a conversation. */
export const TITLE_MAX_LENGTH = 80;

/** Ends an automatic title that was cut short. */
export const TITLE_ELLIPSIS = "…";
