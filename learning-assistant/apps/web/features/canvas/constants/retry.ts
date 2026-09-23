import type { RetryableMessageTask } from "@/features/canvas/types/retry";

/** The chat message Retry sends for each failed task. */
export const RETRY_MESSAGES: Record<RetryableMessageTask, string> = {
  research: "Please try the research again.",
  material: "Please make the learning material again.",
  simplify: "Please try simplifying my learning material again.",
  quiz: "Please write the quiz again.",
};

export const RETRY_LABEL = "Retry";
