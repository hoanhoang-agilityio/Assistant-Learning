import { CheckCircle2, RefreshCw, RotateCcw, Send } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";

export interface QuizActionBarViewProps {
  answeredCount: number;
  total: number;
  canSubmit: boolean;
  canRetake: boolean;
  canAskNew: boolean;
  isSubmitted: boolean;
  onSubmit?: () => void;
  onRetake?: () => void;
  onNewQuestions?: () => void;
}

const SECONDARY_BUTTON_CLASS =
  "flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:border-slate-700 dark:hover:bg-slate-800";

/** Answered count and progress bar, then Retake, New questions and Submit. */
export const QuizActionBarView = ({
  answeredCount,
  total,
  canSubmit,
  canRetake,
  canAskNew,
  isSubmitted,
  onSubmit,
  onRetake,
  onNewQuestions,
}: QuizActionBarViewProps) => (
  <section
    className={`${CARD_CLASS} flex flex-wrap items-center justify-between gap-4`}
  >
    <div className="min-w-40 flex-1">
      <p className="mb-2 text-xs font-medium text-slate-600 dark:text-slate-300">
        {isSubmitted
          ? "Submitted — your answers are graded above."
          : `${answeredCount} of ${total} answered`}
      </p>
      <div
        role="progressbar"
        aria-label="Questions answered"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={answeredCount}
        className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"
      >
        <div
          className="h-full rounded-full bg-indigo-600 transition-all"
          style={{ width: `${total ? (answeredCount / total) * 100 : 0}%` }}
        />
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={!canRetake}
        onClick={onRetake}
        className={SECONDARY_BUTTON_CLASS}
      >
        <RotateCcw className="h-3.5 w-3.5" /> Retake
      </button>
      <button
        type="button"
        disabled={!canAskNew}
        onClick={onNewQuestions}
        className={SECONDARY_BUTTON_CLASS}
      >
        <RefreshCw className="h-3.5 w-3.5" /> New questions
      </button>
      {isSubmitted ? (
        <span className="flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
          <CheckCircle2 className="h-3.5 w-3.5" /> Submitted
        </span>
      ) : (
        <button
          type="button"
          disabled={!canSubmit}
          onClick={onSubmit}
          title={canSubmit ? undefined : "Answer every question first"}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-indigo-600"
        >
          <Send className="h-3.5 w-3.5" /> Submit
        </button>
      )}
    </div>
  </section>
);
