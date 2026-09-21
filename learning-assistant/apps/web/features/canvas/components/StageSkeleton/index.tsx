import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { StageStep } from "@/features/canvas/types/canvas";

export interface StageSkeletonProps {
  step: StageStep;
}

/** A stage whose subagent is running. */
export const StageSkeleton = ({ step }: StageSkeletonProps) => (
  <div className={`${CARD_CLASS} space-y-4`} role="status" aria-live="polite">
    <p className="text-xs font-semibold tracking-wider text-indigo-500 uppercase">
      Building {step.title}…
    </p>
    <div className="animate-pulse space-y-3">
      <div className="h-5 w-2/3 rounded-lg bg-slate-200 dark:bg-slate-700" />
      <div className="h-3 w-full rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-3 w-11/12 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-3 w-4/5 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="h-20 w-full rounded-xl bg-slate-100 dark:bg-slate-900/60" />
    </div>
  </div>
);
