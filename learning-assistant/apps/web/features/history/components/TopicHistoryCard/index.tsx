import { WEAK_CONCEPT_PERCENT } from "@repo/shared/constants/memory";
import { HOME_ROUTE, RETAKE_SEARCH_PARAM } from "@repo/shared/constants/routes";
import type { TopicHistory } from "@repo/shared/schemas";
import { RotateCcw } from "lucide-react";
import Link from "next/link";

import { ScoreTrendChart } from "@/features/history/components/ScoreTrendChart";
import { HISTORY_COPY } from "@/features/history/constants/history";
import {
  formatScoreChange,
  summarizeTopic,
} from "@/features/history/utils/score-trend";

export interface TopicHistoryCardProps {
  topic: TopicHistory;
}

const STAT_LABEL_CLASS =
  "text-[10px] font-semibold tracking-wider text-slate-400 uppercase";

/** One topic: its latest and best score, scores by attempt, concept mastery and Retake. */
export const TopicHistoryCard = ({ topic }: TopicHistoryCardProps) => {
  const title = topic.title ?? HISTORY_COPY.untitled;
  const { latestPercent, bestPercent, change } = summarizeTopic(topic);
  const tier = topic.attempts.at(-1)?.score.tier;
  const mastery = [...topic.mastery].sort((a, b) => a.percent - b.percent);

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <h2 className="min-w-0 text-base font-semibold break-words">{title}</h2>
        <Link
          href={{
            pathname: HOME_ROUTE,
            query: { [RETAKE_SEARCH_PARAM]: topic.conversationId },
          }}
          className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
        >
          <RotateCcw className="h-3.5 w-3.5" /> {HISTORY_COPY.retake}
        </Link>
      </header>

      <dl className="mb-3 flex flex-wrap gap-x-6 gap-y-2">
        <div>
          <dt className={STAT_LABEL_CLASS}>{HISTORY_COPY.latest}</dt>
          <dd className="flex items-baseline gap-2">
            <span className="text-2xl font-bold tabular-nums">
              {latestPercent}%
            </span>
            {tier && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                {tier}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className={STAT_LABEL_CLASS}>{HISTORY_COPY.best}</dt>
          <dd className="text-2xl font-bold text-slate-500 tabular-nums dark:text-slate-400">
            {bestPercent}%
          </dd>
        </div>
        {change !== null && (
          <p className="self-end pb-1 text-xs text-slate-500 dark:text-slate-400">
            <span className="font-semibold tabular-nums">
              {formatScoreChange(change)}
            </span>{" "}
            {HISTORY_COPY.sinceFirst}
          </p>
        )}
      </dl>

      <ScoreTrendChart attempts={topic.attempts} label={title} />

      <section className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-700">
        <h3 className="mb-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
          {HISTORY_COPY.mastery}
        </h3>
        {mastery.length === 0 ? (
          <p className="text-xs text-slate-400 italic">
            {HISTORY_COPY.noMastery}
          </p>
        ) : (
          <ul className="space-y-2">
            {mastery.map(({ concept, percent }) => {
              const isWeak = percent < WEAK_CONCEPT_PERCENT;
              return (
                <li key={concept}>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="truncate">{concept}</span>
                    {isWeak && (
                      <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                        {HISTORY_COPY.weak}
                      </span>
                    )}
                    <span className="ml-auto text-slate-500 tabular-nums dark:text-slate-400">
                      {percent}%
                    </span>
                  </div>
                  <div
                    role="meter"
                    aria-label={`${concept} mastery`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                    className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"
                  >
                    <div
                      className={`h-full rounded-full ${isWeak ? "bg-amber-500" : "bg-emerald-500"}`}
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </article>
  );
};
