import { DisplayToolCard } from "@/components/common/DisplayToolCard";
import { useIsToolStopped } from "@/features/chat/hooks/use-is-tool-stopped";
import type { ToolCallStatus } from "@/features/chat/types/chat";

export interface SurfaceToolCardProps {
  status: ToolCallStatus;
  result?: string;
  /** A finished call of this kind leaves no card; a stopped one always does. */
  isHiddenWhenDone: boolean;
  detail?: string;
  copy: { running: string; done: string; stopped: string };
}

/**
 * The chat card for a surface or Board tool. A call the student stopped shows
 * a grey stopped card instead of vanishing or spinning on.
 */
export const SurfaceToolCard = ({
  status,
  result,
  isHiddenWhenDone,
  detail,
  copy,
}: SurfaceToolCardProps) => {
  const isStopped = useIsToolStopped(status, result);

  if (!isStopped && status === "complete" && isHiddenWhenDone) {
    return null;
  }

  return (
    <DisplayToolCard
      status={status}
      isStopped={isStopped}
      detail={detail}
      copy={copy}
    />
  );
};
