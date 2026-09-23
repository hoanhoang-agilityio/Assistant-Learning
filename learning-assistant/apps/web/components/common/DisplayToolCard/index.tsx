import { CheckCircle2, Loader2 } from "lucide-react";

import { DISPLAY_TOOL_COPY } from "@/constants/layout";

export interface DisplayToolCardProps {
  /** The status CopilotKit passes to a tool renderer. */
  status: "inProgress" | "executing" | "complete";
  /** What changes, e.g. "dark" or "popup · mobile". */
  detail?: string;
  /** Running and done labels; defaults to the display copy. */
  copy?: { running: string; done: string };
}

/** A one-line chat card for the theme, layout and settings tools. */
export const DisplayToolCard = ({
  status,
  detail,
  copy = DISPLAY_TOOL_COPY,
}: DisplayToolCardProps) => {
  const isDone = status === "complete";

  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
        isDone
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "border-indigo-200 bg-indigo-50/60 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300"
      }`}
    >
      {isDone ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
      ) : (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
      )}
      <span className="font-medium">{isDone ? copy.done : copy.running}</span>
      {detail && <span className="capitalize opacity-70">{detail}</span>}
    </div>
  );
};
