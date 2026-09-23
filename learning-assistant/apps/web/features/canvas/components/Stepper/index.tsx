import { Check } from "lucide-react";

import type { CanvasStage, StepperStep } from "@/features/canvas/types/canvas";

export interface StepperProps {
  steps: StepperStep[];
  /** Bar fill, in percent. */
  progress: number;
  /** 1-based position of the active stage, for screen readers. */
  stageNumber: number;
  stageCount: number;
  onSelectStage: (stage: CanvasStage) => void;
}

/** The six-stage progress bar. Stages with data show a check. */
export const Stepper = ({
  steps,
  progress,
  stageNumber,
  stageCount,
  onSelectStage,
}: StepperProps) => (
  <nav
    aria-label="Learning stages"
    className="border-b border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-800/60"
  >
    <div className="relative mx-auto max-w-4xl">
      <div className="absolute top-[18px] left-0 h-1 w-full rounded-full bg-slate-200 dark:bg-slate-700" />
      <div
        className="absolute top-[18px] left-0 h-1 rounded-full bg-indigo-600 transition-all duration-300"
        style={{ width: `${progress}%` }}
      />
      <ol className="relative flex items-center justify-between">
        {steps.map(
          ({
            id,
            title,
            icon: Icon,
            isActive,
            isUnlocked,
            isCompleted,
            isBuilding,
          }) => {
            const circleClass = isActive
              ? "scale-110 bg-indigo-600 text-white ring-4 ring-indigo-100 dark:ring-indigo-950"
              : isCompleted
                ? "bg-emerald-500 text-white"
                : "border border-slate-200 bg-white text-slate-400 dark:border-slate-700 dark:bg-slate-800";
            const labelClass = isActive
              ? "font-semibold text-indigo-600 dark:text-indigo-400"
              : isCompleted
                ? "text-slate-600 dark:text-slate-300"
                : "text-slate-400";

            return (
              <li key={id} className="relative z-10">
                <button
                  type="button"
                  disabled={!isUnlocked}
                  aria-current={isActive ? "step" : undefined}
                  aria-label={`${title}${isUnlocked ? "" : " (locked)"}`}
                  onClick={() => onSelectStage(id)}
                  className="group flex flex-col items-center gap-1.5 focus:outline-none disabled:cursor-not-allowed"
                >
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-full text-xs font-medium shadow-md transition-all duration-200 group-focus-visible:ring-4 group-focus-visible:ring-indigo-300 ${circleClass} ${isBuilding ? "animate-pulse" : ""}`}
                  >
                    {isCompleted ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Icon className="h-4 w-4" />
                    )}
                  </span>
                  <span
                    className={`hidden text-[11px] font-medium transition-colors @xl:block ${labelClass}`}
                  >
                    {title}
                  </span>
                </button>
              </li>
            );
          },
        )}
      </ol>
    </div>
    <span className="sr-only">
      Stage {stageNumber} of {stageCount}
    </span>
  </nav>
);
