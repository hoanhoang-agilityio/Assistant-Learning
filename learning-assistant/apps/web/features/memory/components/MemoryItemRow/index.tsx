import { Loader2, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { MEMORY_COPY } from "@/features/memory/constants/memory";

export interface MemoryItemRowProps {
  /** What the item is called, for the buttons' labels. */
  label: string;
  /** Something is kept to forget; without it the row has no Forget. */
  canForget?: boolean;
  isConfirming: boolean;
  isForgetting: boolean;
  /** Another save or forget is running. */
  isDisabled: boolean;
  onForgetRequest: () => void;
  onForgetCancel: () => void;
  onForgetConfirm: () => void;
  children: ReactNode;
}

const ROW_BUTTON_CLASS =
  "rounded-md px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-40";

/**
 * One remembered item with Forget. Forget asks first, in place of the
 * button; nothing is forgotten until the second press.
 */
export const MemoryItemRow = ({
  label,
  canForget = true,
  isConfirming,
  isForgetting,
  isDisabled,
  onForgetRequest,
  onForgetCancel,
  onForgetConfirm,
  children,
}: MemoryItemRowProps) => (
  <li className="flex items-center gap-3 py-2">
    <div className="min-w-0 flex-1">{children}</div>
    {!canForget ? null : isConfirming ? (
      <div
        role="group"
        aria-label={`${MEMORY_COPY.forget} ${label}`}
        className="flex shrink-0 items-center gap-1"
      >
        <span className="text-[11px] text-slate-500 dark:text-slate-400">
          {MEMORY_COPY.forgetConfirm}
        </span>
        <button
          type="button"
          onClick={onForgetCancel}
          disabled={isForgetting}
          autoFocus
          className={`${ROW_BUTTON_CLASS} text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700`}
        >
          {MEMORY_COPY.cancel}
        </button>
        <button
          type="button"
          onClick={onForgetConfirm}
          disabled={isDisabled}
          className={`${ROW_BUTTON_CLASS} flex items-center gap-1 bg-rose-600 font-medium text-white hover:bg-rose-700`}
        >
          {isForgetting && <Loader2 className="h-3 w-3 animate-spin" />}
          {MEMORY_COPY.forget}
        </button>
      </div>
    ) : (
      <button
        type="button"
        aria-label={`${MEMORY_COPY.forget} ${label}`}
        onClick={onForgetRequest}
        disabled={isDisabled}
        className={`${ROW_BUTTON_CLASS} flex shrink-0 items-center gap-1 text-slate-500 hover:bg-rose-50 hover:text-rose-600 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-400`}
      >
        <Trash2 className="h-3.5 w-3.5" />
        {MEMORY_COPY.forget}
      </button>
    )}
  </li>
);
