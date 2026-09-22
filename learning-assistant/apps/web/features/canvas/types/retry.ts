import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import type { RunningTask } from "@repo/shared/schemas";

/** Tasks retried by asking the assistant again in chat. */
export type RetryableMessageTask = Exclude<RunningTask, "evaluate">;

/**
 * How Retry repeats a failed task: a chat message to the assistant, or (for
 * grading) the quiz Submit again, which the agent grades in code.
 */
export type RetryAction =
  | { kind: "message"; content: string }
  | { kind: "submit"; action: A2UIClientEventMessage };
