"use client";

import type { SubagentTool } from "@repo/shared/schemas";

import { ToolProgressView } from "@/features/chat/components/ToolProgressView";
import { useToolProgress } from "@/features/chat/hooks/use-tool-progress";
import type { ToolCallStatus } from "@/features/chat/types/chat";

export interface ToolProgressProps {
  tool: SubagentTool;
  status: ToolCallStatus;
  /** Short context after the label, e.g. the research topic. */
  detail?: string;
  result?: string;
}

/** Progress card for one subagent tool call, rendered in the chat. */
export const ToolProgress = ({
  tool,
  status,
  detail,
  result,
}: ToolProgressProps) => {
  const { phase, title, error, seconds, handleStop } = useToolProgress(
    tool,
    status,
    detail,
    result,
  );

  return (
    <ToolProgressView
      phase={phase}
      title={title}
      error={error}
      seconds={seconds}
      onStop={handleStop}
    />
  );
};
