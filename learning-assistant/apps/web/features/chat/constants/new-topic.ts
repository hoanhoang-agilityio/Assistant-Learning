/** What the Supervisor reads about the new-topic confirmation tool. */
export const NEW_TOPIC_TOOL_DESCRIPTION =
  "Ask the student to confirm switching to a new topic, because it clears the current research, notes, quiz and results. Call it only when notes or a quiz exist, then wait for the result before calling research.";

/** Stands in for the current topic when state has none. */
export const CURRENT_TOPIC_FALLBACK = "the current topic";

/** Copy on the new-topic confirmation card. */
export const NEW_TOPIC_COPY = {
  preparing: "Preparing a new topic…",
  title: "Start a new topic?",
  confirm: "Start new topic",
  keep: "Keep current topic",
  confirmed: "New topic started",
  kept: "Kept the current topic",
} as const;
