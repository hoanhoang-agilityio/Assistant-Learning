import { RotateCcw } from "lucide-react";

import { RETRY_LABEL } from "@/features/canvas/constants/retry";

export interface StageErrorProps {
  message: string;
  /** Shows a Retry button that repeats the failed task. */
  onRetry?: () => void;
  isRetryDisabled?: boolean;
}

/** A failed task or surface, with Retry when the task can be repeated. */
export const StageError = ({
  message,
  onRetry,
  isRetryDisabled = false,
}: StageErrorProps) => (
  <div
    role="alert"
    className="flex items-start gap-3 rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-xs text-rose-700 dark:text-rose-300"
  >
    <p className="min-w-0 flex-1 break-words">
      <strong className="font-semibold">Something went wrong:</strong> {message}
    </p>
    {onRetry && (
      <button
        type="button"
        disabled={isRetryDisabled}
        onClick={onRetry}
        className="flex shrink-0 items-center gap-1 rounded-lg border border-current/30 px-2 py-1 text-[11px] font-medium transition-colors hover:bg-white/60 disabled:opacity-40 disabled:hover:bg-transparent dark:hover:bg-slate-900/60"
      >
        <RotateCcw className="h-3 w-3" />
        {RETRY_LABEL}
      </button>
    )}
  </div>
);
