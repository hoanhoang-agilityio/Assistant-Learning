import type { LearningState } from "@repo/shared/schemas";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { StageEmpty } from "@/features/canvas/components/StageEmpty";
import { StageError } from "@/features/canvas/components/StageError";
import { StagePreview } from "@/features/canvas/components/StagePreview";
import { StageSkeleton } from "@/features/canvas/components/StageSkeleton";
import { Stepper } from "@/features/canvas/components/Stepper";
import type {
  CanvasStage,
  StageStep,
  StepperStep,
} from "@/features/canvas/types/canvas";

export interface CanvasShellViewProps {
  state: LearningState;
  activeStage: CanvasStage;
  step: StageStep;
  /** 1-based position of the active stage. */
  stageNumber: number;
  stageCount: number;
  steps: StepperStep[];
  /** Stepper bar fill, in percent. */
  progress: number;
  isBuilding: boolean;
  hasData: boolean;
  error: string | null;
  hasPrev: boolean;
  hasNext: boolean;
  onSelectStage: (stage: CanvasStage) => void;
  onPrev: () => void;
  onNext: () => void;
}

/** Right panel: the stepper, the stage header with Prev/Next, and the stage. */
export const CanvasShellView = ({
  state,
  activeStage,
  step,
  stageNumber,
  stageCount,
  steps,
  progress,
  isBuilding,
  hasData,
  error,
  hasPrev,
  hasNext,
  onSelectStage,
  onPrev,
  onNext,
}: CanvasShellViewProps) => (
  <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-50/50 dark:bg-slate-900/50">
    <Stepper
      steps={steps}
      progress={progress}
      stageNumber={stageNumber}
      stageCount={stageCount}
      onSelectStage={onSelectStage}
    />

    <div className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-6 py-2 dark:border-slate-800 dark:bg-slate-800/40">
      <div className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 rounded-md bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-600 dark:bg-indigo-950/80 dark:text-indigo-300">
          Stage {stageNumber} of {stageCount}
        </span>
        <h2 className="text-sm font-bold">{step.title}</h2>
        <span className="hidden truncate text-xs text-slate-400 md:inline">
          — {step.description}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          aria-label="Previous stage"
          disabled={!hasPrev}
          onClick={onPrev}
          className="rounded-lg border border-slate-200 p-1.5 text-xs font-medium hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent dark:border-slate-700 dark:hover:bg-slate-800"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          type="button"
          disabled={!hasNext}
          onClick={onNext}
          className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-all hover:bg-indigo-700 disabled:opacity-40 disabled:hover:bg-indigo-600"
        >
          <span>Next Stage</span>
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>

    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {error && <StageError message={error} />}
        {isBuilding ? (
          <StageSkeleton step={step} />
        ) : hasData ? (
          <StagePreview stage={activeStage} state={state} />
        ) : (
          <StageEmpty step={step} />
        )}
      </div>
    </div>
  </main>
);
