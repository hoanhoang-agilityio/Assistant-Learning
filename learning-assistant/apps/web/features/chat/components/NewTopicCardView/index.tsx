import { ArrowRightLeft, Check } from "lucide-react";

import {
  CURRENT_TOPIC_FALLBACK,
  NEW_TOPIC_COPY,
} from "@/features/chat/constants/new-topic";

export interface NewTopicCardViewProps {
  topic?: string;
  currentTopic: string | null;
  /** The tool call is still streaming its arguments. */
  isPreparing: boolean;
  /** The student's answer once the call is complete, else `null`. */
  isConfirmed: boolean | null;
  canAnswer: boolean;
  onConfirm: () => void;
  onKeep: () => void;
}

/** A confirm / keep card in the chat, then a one-line record of the answer. */
export const NewTopicCardView = ({
  topic,
  currentTopic,
  isPreparing,
  isConfirmed,
  canAnswer,
  onConfirm,
  onKeep,
}: NewTopicCardViewProps) => {
  if (isPreparing) {
    return (
      <div
        role="status"
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
      >
        {NEW_TOPIC_COPY.preparing}
      </div>
    );
  }

  if (isConfirmed !== null) {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300"
      >
        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
        <span>
          {isConfirmed
            ? `${NEW_TOPIC_COPY.confirmed}: ${topic}`
            : NEW_TOPIC_COPY.kept}
        </span>
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label={NEW_TOPIC_COPY.title}
      className="space-y-3 rounded-xl border border-amber-300/60 bg-amber-50 px-3 py-3 text-xs text-slate-700 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-slate-200"
    >
      <div className="flex items-start gap-2.5">
        <ArrowRightLeft className="mt-px h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="min-w-0">
          <p className="font-semibold">{NEW_TOPIC_COPY.title}</p>
          <p className="mt-0.5 text-slate-600 dark:text-slate-400">
            Switching to <strong>“{topic}”</strong> clears the research, notes,
            quiz and results for{" "}
            {currentTopic ? `“${currentTopic}”` : CURRENT_TOPIC_FALLBACK}. This
            chat stays.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canAnswer}
          onClick={onConfirm}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-40 disabled:hover:bg-indigo-600"
        >
          {NEW_TOPIC_COPY.confirm}
        </button>
        <button
          type="button"
          disabled={!canAnswer}
          onClick={onKeep}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium transition-colors hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          {NEW_TOPIC_COPY.keep}
        </button>
      </div>
    </div>
  );
};
