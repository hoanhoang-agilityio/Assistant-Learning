import { HOME_ROUTE } from "@repo/shared/constants/routes";
import type { LearningHistory } from "@repo/shared/schemas";
import { ArrowLeft, TrendingUp } from "lucide-react";
import Link from "next/link";

import { TopicHistoryCard } from "@/features/history/components/TopicHistoryCard";
import { HISTORY_COPY } from "@/features/history/constants/history";

export interface HistoryViewProps {
  history: LearningHistory;
}

/** The History / Progress page: one card per topic, the most recently graded first. */
export const HistoryView = ({ history }: HistoryViewProps) => (
  <div className="w-full max-w-2xl space-y-4 py-4">
    <Link
      href={HOME_ROUTE}
      className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> {HISTORY_COPY.back}
    </Link>
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-tr from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
        <TrendingUp className="h-5 w-5" />
      </div>
      <div>
        <h1 className="text-lg leading-tight font-bold tracking-tight">
          {HISTORY_COPY.title}
        </h1>
        <p className="text-xs text-slate-400">{HISTORY_COPY.intro}</p>
      </div>
    </div>

    {history.topics.length === 0 ? (
      <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-600 dark:text-slate-400">
        {HISTORY_COPY.empty}
      </p>
    ) : (
      history.topics.map((topic) => (
        <TopicHistoryCard key={topic.conversationId} topic={topic} />
      ))
    )}
  </div>
);
