import type { ConversationSummary } from "@repo/shared/schemas";
import { Pencil, Trash2 } from "lucide-react";

import { ConversationDeleteConfirm } from "@/features/conversations/components/ConversationDeleteConfirm";
import { ConversationTitleForm } from "@/features/conversations/components/ConversationTitleForm";
import {
  CONVERSATION_COPY,
  STAGE_LABELS,
  STATUS_LABELS,
} from "@/features/conversations/constants/conversations";
import {
  formatScore,
  getConversationTitle,
} from "@/features/conversations/utils/conversations";

export interface ConversationRowViewProps {
  conversation: ConversationSummary;
  isActive: boolean;
  isEditing: boolean;
  isDeleting: boolean;
  isBusy: boolean;
  onSelect: (id: string) => void;
  onStartRename: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onCancelRename: () => void;
  onRequestDelete: (id: string) => void;
  onDelete: (id: string) => void;
  onCancelDelete: () => void;
}

const STATUS_BADGE_CLASS: Record<ConversationSummary["status"], string> = {
  active:
    "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
  completed:
    "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
  abandoned:
    "bg-slate-100 text-slate-500 dark:bg-slate-700/60 dark:text-slate-400",
};

const BADGE_CLASS = "rounded-full px-1.5 py-0.5 text-[10px] font-medium";

const ROW_CLASS = "group relative rounded-lg border transition-colors";

const ROW_ACTIVE_CLASS =
  "border-indigo-300 bg-white shadow-sm dark:border-indigo-500/40 dark:bg-slate-800";

const ROW_IDLE_CLASS =
  "border-slate-200 hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:hover:border-slate-700 dark:hover:bg-slate-800/60";

const ACTION_BUTTON_CLASS =
  "rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200";

/** One conversation: its title, stage, status and score, with rename and delete. */
export const ConversationRowView = ({
  conversation,
  isActive,
  isEditing,
  isDeleting,
  isBusy,
  onSelect,
  onStartRename,
  onRename,
  onCancelRename,
  onRequestDelete,
  onDelete,
  onCancelDelete,
}: ConversationRowViewProps) => {
  const title = getConversationTitle(conversation);
  const { id, stage, status, score } = conversation;

  if (isDeleting) {
    return (
      <li>
        <ConversationDeleteConfirm
          title={title}
          isBusy={isBusy}
          onConfirm={() => onDelete(id)}
          onCancel={onCancelDelete}
        />
      </li>
    );
  }

  if (isEditing) {
    return (
      <li className="rounded-lg border border-indigo-300 bg-white dark:border-indigo-500/40 dark:bg-slate-800">
        <ConversationTitleForm
          initialTitle={conversation.title ?? ""}
          isBusy={isBusy}
          onSave={(next) => onRename(id, next)}
          onCancel={onCancelRename}
        />
      </li>
    );
  }

  return (
    <li
      className={`${ROW_CLASS} ${isActive ? ROW_ACTIVE_CLASS : ROW_IDLE_CLASS}`}
    >
      <button
        type="button"
        onClick={() => onSelect(id)}
        aria-current={isActive ? "true" : undefined}
        className="w-full px-2.5 py-2 pr-14 text-left"
      >
        <span className="block truncate text-xs font-medium text-slate-800 dark:text-slate-100">
          {title}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-slate-500 dark:text-slate-400">
            {STAGE_LABELS[stage]}
          </span>
          <span className={`${BADGE_CLASS} ${STATUS_BADGE_CLASS[status]}`}>
            {STATUS_LABELS[status]}
          </span>
          {score && (
            <span
              className={`${BADGE_CLASS} bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300`}
            >
              {formatScore(score)}
            </span>
          )}
        </span>
      </button>
      <div className="absolute top-1.5 right-1.5 flex gap-0.5 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => onStartRename(id)}
          aria-label={`${CONVERSATION_COPY.rename} ${title}`}
          title={CONVERSATION_COPY.rename}
          className={ACTION_BUTTON_CLASS}
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={() => onRequestDelete(id)}
          aria-label={`${CONVERSATION_COPY.delete} ${title}`}
          title={CONVERSATION_COPY.delete}
          className={ACTION_BUTTON_CLASS}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </li>
  );
};
