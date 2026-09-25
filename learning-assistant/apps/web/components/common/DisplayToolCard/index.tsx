import { CheckCircle2, CircleSlash, Loader2 } from "lucide-react";

import { DISPLAY_TOOL_COPY } from "@/constants/layout";

type DisplayToolLook = "running" | "done" | "stopped";

/** Stopped is grey, like a stopped subagent card: nothing went wrong. */
const LOOK_STYLES: Record<DisplayToolLook, string> = {
  running:
    "border-indigo-200 bg-indigo-50/60 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300",
  done: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  stopped:
    "border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400",
};

export interface DisplayToolCardProps {
  /** The status CopilotKit passes to a tool renderer. */
  status: "inProgress" | "executing" | "complete";
  /** The student stopped the call; wins over `status`. */
  isStopped?: boolean;
  /** What changes, e.g. "dark" or "popup · mobile". */
  detail?: string;
  /** Running, done and stopped labels; defaults to the display copy. */
  copy?: { running: string; done: string; stopped?: string };
}

/** A one-line chat card for the display, settings and Board tools. */
export const DisplayToolCard = ({
  status,
  isStopped = false,
  detail,
  copy = DISPLAY_TOOL_COPY,
}: DisplayToolCardProps) => {
  const look: DisplayToolLook = isStopped
    ? "stopped"
    : status === "complete"
      ? "done"
      : "running";
  const label =
    look === "stopped"
      ? (copy.stopped ?? DISPLAY_TOOL_COPY.stopped)
      : copy[look];

  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${LOOK_STYLES[look]}`}
    >
      {look === "running" && (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
      )}
      {look === "done" && (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
      )}
      {look === "stopped" && <CircleSlash className="h-4 w-4 shrink-0" />}
      <span className="font-medium">{label}</span>
      {detail && <span className="capitalize opacity-70">{detail}</span>}
    </div>
  );
};
