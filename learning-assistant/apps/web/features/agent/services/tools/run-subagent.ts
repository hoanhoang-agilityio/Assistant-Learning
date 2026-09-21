import type { SubagentTool, ToolResultData } from "@repo/shared/schemas";

import {
  TOOL_ERRORS,
  TOOL_FAILURE_PREFIX,
} from "@/features/agent/constants/tools";

interface ToolFailure {
  ok: false;
  error: string;
}

export const fail = (error: string): ToolFailure => ({ ok: false, error });

/**
 * Runs a subagent and turns any throw into `{ ok: false, error }`. Tools never
 * throw: the wrapper reads the failure into `status.error` and the Supervisor
 * sees it in the tool result, so it can explain instead of retrying blindly.
 */
export const runSubagent = async <T extends SubagentTool>(
  tool: T,
  signal: AbortSignal,
  work: () => Promise<ToolResultData<T>>,
): Promise<{ ok: true; data: ToolResultData<T> } | ToolFailure> => {
  try {
    return { ok: true, data: await work() };
  } catch (error) {
    if (signal.aborted) return fail(TOOL_ERRORS.stopped);
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[${tool}]`, error);
    return fail(`${TOOL_FAILURE_PREFIX[tool]}: ${message}`);
  }
};
