import type { Score } from "@repo/shared/schemas";
import { ArrowRight, Sparkles } from "lucide-react";

import { FEEDBACK_READY_COPY } from "@/features/chat/constants/tools";

export interface FeedbackReadyCardViewProps {
  score: Score;
  onOpen: () => void;
}

/** A button card that opens the Feedback stage. */
export const FeedbackReadyCardView = ({
  score,
  onOpen,
}: FeedbackReadyCardViewProps) => (
  <button
    type="button"
    onClick={onOpen}
    className="group flex w-full items-center gap-3 rounded-xl border border-indigo-200 bg-white px-3 py-2.5 text-left text-xs shadow-sm transition-colors hover:border-indigo-400 hover:bg-indigo-50 dark:border-indigo-900/60 dark:bg-slate-800 dark:hover:bg-indigo-950/50"
  >
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white">
      <Sparkles className="h-4 w-4" />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block font-semibold">{FEEDBACK_READY_COPY.title}</span>
      <span className="block text-slate-500 dark:text-slate-400">
        {score.tier} · {score.percent}% — {FEEDBACK_READY_COPY.hint}
      </span>
    </span>
    <ArrowRight className="h-4 w-4 shrink-0 text-indigo-500 transition-transform group-hover:translate-x-0.5" />
  </button>
);
