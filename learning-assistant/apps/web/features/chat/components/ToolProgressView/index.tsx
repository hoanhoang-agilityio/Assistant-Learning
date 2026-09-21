import { Square } from "lucide-react";

import { PhaseIcon } from "@/features/chat/components/PhaseIcon";
import type { ToolPhase } from "@/features/chat/types/chat";

const PHASE_STYLES: Record<ToolPhase, string> = {
  running:
    "border-indigo-200 bg-indigo-50/60 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300",
  done: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  failed: "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  stopped:
    "border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400",
};

export interface ToolProgressViewProps {
  phase: ToolPhase;
  title: string;
  error: string | null;
  /** Seconds since the call started; shown while running. */
  seconds: number;
  onStop: () => void;
}

/** The card itself: phase icon, headline, error or timer, and a Stop button. */
export const ToolProgressView = ({
  phase,
  title,
  error,
  seconds,
  onStop,
}: ToolProgressViewProps) => {
  const isRunning = phase === "running";

  return (
    <div
      role="status"
      className={`flex items-start gap-2.5 rounded-xl border px-3 py-2 text-xs ${PHASE_STYLES[phase]}`}
    >
      <span className="mt-px">
        <PhaseIcon phase={phase} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium break-words">{title}</p>
        {error && <p className="mt-0.5 opacity-90">{error}</p>}
        {isRunning && (
          <p className="mt-0.5 tabular-nums opacity-70">{seconds}s</p>
        )}
      </div>
      {isRunning && (
        <button
          type="button"
          onClick={onStop}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-current/20 px-2 py-1 text-[11px] font-medium transition-colors hover:bg-white/60 dark:hover:bg-slate-900/60"
        >
          <Square className="h-3 w-3 fill-current" />
          Stop
        </button>
      )}
    </div>
  );
};
