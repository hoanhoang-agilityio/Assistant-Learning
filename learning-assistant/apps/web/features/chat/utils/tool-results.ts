import {
  type Score,
  type SubagentTool,
  ToolResultSchemas,
} from "@repo/shared/schemas";

import { TOOL_LABELS } from "@/features/chat/constants/tools";
import type { ToolCallStatus, ToolPhase } from "@/features/chat/types/chat";

/**
 * Reads the error from a subagent tool's result string. Tools return
 * `{ ok: false, error }` instead of throwing; anything else counts as success.
 */
export const parseToolError = (result: string | undefined): string | null => {
  if (!result) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(result);
    if (
      parsed &&
      typeof parsed === "object" &&
      "ok" in parsed &&
      parsed.ok === false
    ) {
      return "error" in parsed && typeof parsed.error === "string"
        ? parsed.error
        : "Something went wrong.";
    }
    return null;
  } catch {
    return null;
  }
};

/**
 * A tool call still streaming counts as running while the agent runs, and as
 * stopped once it doesn't. A finished call is failed or done by its result.
 */
export const getToolPhase = (
  status: ToolCallStatus,
  isRunning: boolean,
  error: string | null,
): ToolPhase => {
  if (status !== "complete") {
    return isRunning ? "running" : "stopped";
  }
  return error ? "failed" : "done";
};

/** The progress card's headline, with `detail` (e.g. the topic) when given. */
export const formatToolTitle = (
  tool: SubagentTool,
  phase: ToolPhase,
  detail?: string,
): string => {
  const labels = TOOL_LABELS[tool];
  switch (phase) {
    case "running":
      return `${labels.running}${detail ? ` “${detail}”` : ""}…`;
    case "done":
      return detail ? `${labels.done}: ${detail}` : labels.done;
    case "failed":
      return labels.failed;
    case "stopped":
      return labels.stopped;
  }
};

/** "8 questions" from a successful `generateQuiz` result, else `undefined`. */
export const formatQuizSize = (
  result: string | undefined,
): string | undefined => {
  if (!result) {
    return undefined;
  }
  try {
    const parsed = ToolResultSchemas.generateQuiz.safeParse(JSON.parse(result));
    return parsed.success && parsed.data.ok
      ? `${parsed.data.data.quiz.questions.length} questions`
      : undefined;
  } catch {
    return undefined;
  }
};

/** The score from a successful `evaluate` result, else `null`. */
export const parseEvaluateScore = (
  result: string | undefined,
): Score | null => {
  if (!result) {
    return null;
  }
  try {
    const parsed = ToolResultSchemas.evaluate.safeParse(JSON.parse(result));
    return parsed.success && parsed.data.ok ? parsed.data.data.score : null;
  } catch {
    return null;
  }
};
