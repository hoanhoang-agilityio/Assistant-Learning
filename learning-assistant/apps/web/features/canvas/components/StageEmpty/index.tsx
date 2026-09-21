import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { StageStep } from "@/features/canvas/types/canvas";

export interface StageEmptyProps {
  step: StageStep;
}

/** A stage with no data yet: says what to do to fill it. */
export const StageEmpty = ({ step }: StageEmptyProps) => {
  const Icon = step.icon;
  return (
    <div
      className={`${CARD_CLASS} flex min-h-64 flex-col items-center justify-center gap-3 text-center`}
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-500 dark:bg-indigo-950/60 dark:text-indigo-300">
        <Icon className="h-6 w-6" />
      </span>
      <h3 className="text-sm font-bold">Nothing here yet</h3>
      <p className="max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {step.emptyHint}
      </p>
    </div>
  );
};
