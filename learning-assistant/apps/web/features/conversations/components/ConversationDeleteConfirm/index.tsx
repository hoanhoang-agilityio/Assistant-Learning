import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";

export interface ConversationDeleteConfirmProps {
  title: string;
  isBusy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** The step before a delete, in place of the row. Nothing is deleted until Delete. */
export const ConversationDeleteConfirm = ({
  title,
  isBusy,
  onConfirm,
  onCancel,
}: ConversationDeleteConfirmProps) => (
  <div
    role="alertdialog"
    aria-label={`${CONVERSATION_COPY.delete} ${title}`}
    className="space-y-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs dark:border-rose-500/30 dark:bg-rose-500/10"
  >
    <p className="font-medium break-words text-slate-800 dark:text-slate-100">
      {title}
    </p>
    <p className="text-slate-600 dark:text-slate-300">
      {CONVERSATION_COPY.deleteConfirm}
    </p>
    <div className="flex justify-end gap-2">
      <button
        type="button"
        onClick={onCancel}
        autoFocus
        className="rounded-md px-2 py-1 text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-800"
      >
        {CONVERSATION_COPY.cancel}
      </button>
      <button
        type="button"
        onClick={onConfirm}
        disabled={isBusy}
        className="rounded-md bg-rose-600 px-2 py-1 font-medium text-white hover:bg-rose-700 disabled:opacity-50"
      >
        {CONVERSATION_COPY.delete}
      </button>
    </div>
  </div>
);
