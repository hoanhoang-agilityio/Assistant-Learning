import { useCopilotKit } from "@copilotkit/react-core/v2";
import type { SubagentTool } from "@repo/shared/schemas";

import { useElapsedSeconds } from "@/features/chat/hooks/use-elapsed-seconds";
import type { ToolCallStatus } from "@/features/chat/types/chat";
import {
  formatToolTitle,
  getToolPhase,
  parseToolError,
} from "@/features/chat/utils/tool-results";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/** Phase, headline, error and timer for one subagent tool call's card. */
export const useToolProgress = (
  tool: SubagentTool,
  status: ToolCallStatus,
  detail?: string,
  result?: string,
) => {
  const { copilotkit } = useCopilotKit();
  const { agent, isRunning } = useLearningAgent();
  const error = status === "complete" ? parseToolError(result) : null;
  const phase = getToolPhase(status, isRunning, error);
  const seconds = useElapsedSeconds(phase === "running");

  const handleStop = () => copilotkit.stopAgent({ agent });

  return {
    phase,
    title: formatToolTitle(tool, phase, detail),
    error,
    seconds,
    handleStop,
  };
};
