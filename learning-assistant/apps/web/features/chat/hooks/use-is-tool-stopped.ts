import type { ToolCallStatus } from "@/features/chat/types/chat";
import { isToolStopped } from "@/features/chat/utils/tool-results";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/** Whether the student stopped this chat tool call (see `isToolStopped`). */
export const useIsToolStopped = (
  status: ToolCallStatus,
  result: string | undefined,
): boolean => {
  const { isRunning } = useLearningAgent();

  return isToolStopped(status, isRunning, result);
};
