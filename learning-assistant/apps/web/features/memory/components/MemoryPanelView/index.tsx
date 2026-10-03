import { HOME_ROUTE } from "@repo/shared/constants/routes";
import type { LearningLevel, StudentMemory } from "@repo/shared/schemas";
import { AlertTriangle, ArrowLeft, Brain, Loader2 } from "lucide-react";
import Link from "next/link";
import type { SubmitEvent } from "react";

import { MemoryItemRow } from "@/features/memory/components/MemoryItemRow";
import { MemoryProfileFormView } from "@/features/memory/components/MemoryProfileFormView";
import { MemorySection } from "@/features/memory/components/MemorySection";
import { MEMORY_COPY } from "@/features/memory/constants/memory";
import type {
  MemoryItemRef,
  ProfileFormValues,
  ProfileTextField,
} from "@/features/memory/types/memory";
import {
  isSameMemoryItem,
  isWeakConcept,
} from "@/features/memory/utils/memory";

export interface MemoryPanelViewProps {
  /** `null` while loading. */
  memory: StudentMemory | null;
  loadError: string | null;
  values: ProfileFormValues;
  canSave: boolean;
  isSaving: boolean;
  isBusy: boolean;
  confirming: MemoryItemRef | null;
  forgetting: MemoryItemRef | null;
  notice: string | null;
  actionError: string | null;
  onRetry: () => void;
  onLevelChange: (level: LearningLevel | null) => void;
  onTextChange: (field: ProfileTextField, text: string) => void;
  onSave: (event: SubmitEvent<HTMLFormElement>) => void;
  onForgetRequest: (item: MemoryItemRef) => void;
  onForgetCancel: () => void;
  onForgetConfirm: () => void;
}

const EMPTY_CLASS = "py-2 text-xs text-slate-400 italic";
const LIST_CLASS = "divide-y divide-slate-100 dark:divide-slate-700/60";

/** What is kept about the student, with edit and Forget for each part. */
export const MemoryPanelView = ({
  memory,
  loadError,
  values,
  canSave,
  isSaving,
  isBusy,
  confirming,
  forgetting,
  notice,
  actionError,
  onRetry,
  onLevelChange,
  onTextChange,
  onSave,
  onForgetRequest,
  onForgetCancel,
  onForgetConfirm,
}: MemoryPanelViewProps) => {
  const rowProps = (item: MemoryItemRef, label: string) => ({
    label,
    isConfirming: isSameMemoryItem(confirming, item),
    isForgetting: isSameMemoryItem(forgetting, item),
    isDisabled: isBusy,
    onForgetRequest: () => onForgetRequest(item),
    onForgetCancel,
    onForgetConfirm,
  });

  return (
    <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8 dark:border-slate-700 dark:bg-slate-800">
      <Link
        href={HOME_ROUTE}
        className="mb-4 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> {MEMORY_COPY.back}
      </Link>
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-tr from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
          <Brain className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-lg leading-tight font-bold tracking-tight">
            {MEMORY_COPY.title}
          </h1>
          <p className="text-xs text-slate-400">{MEMORY_COPY.intro}</p>
        </div>
      </div>

      {loadError ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
        >
          <span className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> {loadError}
          </span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-rose-300 px-2 py-1 text-xs font-medium hover:bg-white dark:border-rose-500/40 dark:hover:bg-slate-800"
          >
            {MEMORY_COPY.retry}
          </button>
        </div>
      ) : !memory ? (
        <p
          role="status"
          className="flex items-center gap-2 py-6 text-sm text-slate-500 dark:text-slate-400"
        >
          <Loader2 className="h-4 w-4 animate-spin" /> {MEMORY_COPY.loading}
        </p>
      ) : (
        <div className="space-y-5">
          <p
            aria-live="polite"
            className={notice || actionError ? "text-xs" : "sr-only"}
          >
            {actionError ? (
              <span className="text-rose-600 dark:text-rose-400">
                {actionError}
              </span>
            ) : (
              <span className="text-emerald-600 dark:text-emerald-400">
                {notice}
              </span>
            )}
          </p>

          <MemorySection
            title={MEMORY_COPY.profile}
            hint={MEMORY_COPY.profileHint}
          >
            <MemoryProfileFormView
              saved={memory.profile}
              values={values}
              canSave={canSave}
              isSaving={isSaving}
              isBusy={isBusy}
              confirming={confirming}
              forgetting={forgetting}
              onLevelChange={onLevelChange}
              onTextChange={onTextChange}
              onSave={onSave}
              onForgetRequest={onForgetRequest}
              onForgetCancel={onForgetCancel}
              onForgetConfirm={onForgetConfirm}
            />
          </MemorySection>

          <MemorySection
            title={MEMORY_COPY.concepts}
            hint={MEMORY_COPY.conceptsHint}
          >
            {memory.concepts.length === 0 ? (
              <p className={EMPTY_CLASS}>{MEMORY_COPY.noConcepts}</p>
            ) : (
              <ul className={LIST_CLASS}>
                {memory.concepts.map((concept) => (
                  <MemoryItemRow
                    key={concept.key}
                    {...rowProps(
                      { kind: "concepts", id: concept.key },
                      concept.concept,
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                      <span className="font-medium break-words">
                        {concept.concept}
                      </span>
                      {isWeakConcept(concept) && (
                        <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                          {MEMORY_COPY.weak}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex items-center gap-2">
                      <div
                        role="meter"
                        aria-label={`${concept.concept} mastery`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={concept.percent}
                        className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"
                      >
                        <div
                          className={`h-full rounded-full ${
                            isWeakConcept(concept)
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                          }`}
                          style={{ width: `${concept.percent}%` }}
                        />
                      </div>
                      <span className="shrink-0 text-xs whitespace-nowrap text-slate-500 tabular-nums dark:text-slate-400">
                        {concept.correct}/{concept.total} · {concept.percent}%
                      </span>
                    </div>
                  </MemoryItemRow>
                ))}
              </ul>
            )}
          </MemorySection>

          <MemorySection
            title={MEMORY_COPY.topics}
            hint={MEMORY_COPY.topicsHint}
          >
            {memory.topics.length === 0 ? (
              <p className={EMPTY_CLASS}>{MEMORY_COPY.noTopics}</p>
            ) : (
              <ul className={LIST_CLASS}>
                {memory.topics.map((topic) => (
                  <MemoryItemRow
                    key={topic.conversationId}
                    {...rowProps(
                      { kind: "topics", id: topic.conversationId },
                      topic.topic,
                    )}
                  >
                    <p className="text-sm font-medium break-words">
                      {topic.topic}
                    </p>
                    <p className="text-xs text-slate-500 tabular-nums dark:text-slate-400">
                      {MEMORY_COPY.best} {topic.bestPercent}% ·{" "}
                      {MEMORY_COPY.latest} {topic.latestPercent}% ·{" "}
                      {topic.attempts}{" "}
                      {topic.attempts === 1
                        ? MEMORY_COPY.attempt
                        : MEMORY_COPY.attempts}
                    </p>
                  </MemoryItemRow>
                ))}
              </ul>
            )}
          </MemorySection>
        </div>
      )}
    </div>
  );
};
