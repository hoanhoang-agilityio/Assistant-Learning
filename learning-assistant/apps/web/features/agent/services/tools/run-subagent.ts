import type { SubagentTool, ToolResultData } from "@repo/shared/schemas";

import {
  TOOL_ERRORS,
  TOOL_FAILURE_PREFIX,
} from "@/features/agent/constants/tools";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { formatProviderError } from "@/features/agent/utils/provider-errors";

interface ToolFailure {
  ok: false;
  error: string;
}

export const fail = (error: string): ToolFailure => ({ ok: false, error });

/**
 * Runs a subagent and turns any throw into `{ ok: false, error }`. Tools never
 * throw: the wrapper reads the failure into `status.error` and the Supervisor
 * sees it in the tool result, so it can explain instead of retrying blindly.
 * A provider failure (bad key, rate limit…) is put in words the student can
 * act on.
 */
export const runSubagent = async <T extends SubagentTool>(
  tool: T,
  { settings, signal }: Pick<SupervisorRunContext, "settings" | "signal">,
  work: () => Promise<ToolResultData<T>>,
): Promise<{ ok: true; data: ToolResultData<T> } | ToolFailure> => {
  try {
    return { ok: true, data: await work() };
  } catch (error) {
    if (signal.aborted) {
      return fail(TOOL_ERRORS.stopped);
    }
    console.error(`[${tool}]`, error);
    return fail(
      `${TOOL_FAILURE_PREFIX[tool]}: ${formatProviderError(error, settings)}`,
    );
  }
};
