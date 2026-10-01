import { TITLE_MAX_LENGTH } from "@repo/shared/constants/conversations";
import { Check, X } from "lucide-react";
import type { KeyboardEvent, SubmitEvent } from "react";

import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";

export interface ConversationTitleFormViewProps {
  title: string;
  canSave: boolean;
  onChange: (title: string) => void;
  onSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  onCancel: () => void;
}

const ICON_BUTTON_CLASS =
  "rounded p-1 text-slate-500 hover:bg-slate-200 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-700";

export const ConversationTitleFormView = ({
  title,
  canSave,
  onChange,
  onSubmit,
  onKeyDown,
  onCancel,
}: ConversationTitleFormViewProps) => (
  <form onSubmit={onSubmit} className="flex items-center gap-1 px-2 py-1.5">
    <input
      autoFocus
      value={title}
      maxLength={TITLE_MAX_LENGTH}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={onKeyDown}
      aria-label={CONVERSATION_COPY.rename}
      className="min-w-0 flex-1 rounded border border-indigo-300 bg-white px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-indigo-500/50 dark:bg-slate-900"
    />
    <button
      type="submit"
      disabled={!canSave}
      aria-label={CONVERSATION_COPY.save}
      title={CONVERSATION_COPY.save}
      className={ICON_BUTTON_CLASS}
    >
      <Check className="h-3.5 w-3.5" />
    </button>
    <button
      type="button"
      onClick={onCancel}
      aria-label={CONVERSATION_COPY.cancel}
      title={CONVERSATION_COPY.cancel}
      className={ICON_BUTTON_CLASS}
    >
      <X className="h-3.5 w-3.5" />
    </button>
  </form>
);
