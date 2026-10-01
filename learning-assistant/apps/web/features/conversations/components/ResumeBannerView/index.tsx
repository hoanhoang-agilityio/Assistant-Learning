import { History, X } from "lucide-react";

import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";

export interface ResumeBannerViewProps {
  message: string;
  onDismiss: () => void;
}

export const ResumeBannerView = ({
  message,
  onDismiss,
}: ResumeBannerViewProps) => (
  <div
    role="status"
    className="flex shrink-0 items-center gap-2 border-b border-indigo-100 bg-indigo-50 px-4 py-2 text-xs text-indigo-700 dark:border-indigo-500/20 dark:bg-indigo-500/10 dark:text-indigo-200"
  >
    <History className="h-3.5 w-3.5 shrink-0" />
    <span className="flex-1">{message}</span>
    <button
      type="button"
      onClick={onDismiss}
      aria-label={CONVERSATION_COPY.resumeDismiss}
      title={CONVERSATION_COPY.resumeDismiss}
      className="rounded p-0.5 hover:bg-indigo-100 dark:hover:bg-indigo-500/20"
    >
      <X className="h-3.5 w-3.5" />
    </button>
  </div>
);
