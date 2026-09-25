import { CONFIRM_NEW_TOPIC_TOOL } from "@repo/shared/constants/agents";
import type {
  SubagentTool,
  ToolResultData,
  TopicConfirmationRequired,
} from "@repo/shared/schemas";
import { traceable } from "langsmith/traceable";

import {
  TOOL_ERRORS,
  TOOL_FAILURE_PREFIX,
  TOPIC_CONFIRMATION_INSTRUCTION,
} from "../../constants/tools";
import type { SupervisorRunContext } from "../../types/agents";
import { formatOpenAIError } from "../../utils/openai-errors";

interface ToolFailure {
  ok: false;
  error: string;
}

export const fail = (error: string): ToolFailure => ({ ok: false, error });

/**
 * `research` refuses until the student confirms the new topic. Unlike
 * `fail`, the wrapper leaves the state as it is and the chat shows no error.
 */
export const requireTopicConfirmation = (
  topic: string,
): TopicConfirmationRequired => ({
  ok: false,
  requires: CONFIRM_NEW_TOPIC_TOOL,
  topic,
  instruction: TOPIC_CONFIRMATION_INSTRUCTION,
});

/**
 * Runs a subagent and turns any throw into `{ ok: false, error }`. Tools never
 * throw: the wrapper reads the failure into `status.error` and the Supervisor
 * sees it in the tool result, so it can explain instead of retrying blindly.
 * An OpenAI failure (bad key, rate limit…) is put in words the student can
 * act on. With `LANGSMITH_TRACING` on, the subagent's LLM calls are traced
 * under one span named after the tool.
 */
export const runSubagent = async <T extends SubagentTool>(
  tool: T,
  { signal }: Pick<SupervisorRunContext, "signal">,
  work: () => Promise<ToolResultData<T>>,
): Promise<{ ok: true; data: ToolResultData<T> } | ToolFailure> => {
  try {
    const traced = traceable(work, { name: tool, run_type: "chain" });
    return { ok: true, data: await traced() };
  } catch (error) {
    if (signal.aborted) {
      return fail(TOOL_ERRORS.stopped);
    }
    console.error(`[${tool}]`, error);
    return fail(`${TOOL_FAILURE_PREFIX[tool]}: ${formatOpenAIError(error)}`);
  }
};
