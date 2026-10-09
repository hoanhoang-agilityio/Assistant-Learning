import type { ChatStatus } from "@/features/chat/types/chat";

const STATUS_LABELS: Record<ChatStatus, string> = {
  starting: "Starting",
  online: "Online",
  thinking: "Thinking",
  offline: "Offline",
};

const STATUS_STYLES: Record<ChatStatus, string> = {
  starting:
    "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  online:
    "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  thinking:
    "border-indigo-500/20 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  offline: "border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-400",
};

const DOT_STYLES: Record<ChatStatus, string> = {
  starting: "animate-pulse bg-amber-500",
  online: "bg-emerald-500",
  thinking: "animate-pulse bg-indigo-500",
  offline: "bg-rose-500",
};

export interface ChatStatusBadgeProps {
  status: ChatStatus;
}

/** The chat header pill: a coloured dot and the status label. */
export const ChatStatusBadge = ({ status }: ChatStatusBadgeProps) => (
  <span
    role="status"
    className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLES[status]}`}
  >
    <span className={`h-1.5 w-1.5 rounded-full ${DOT_STYLES[status]}`} />
    {STATUS_LABELS[status]}
  </span>
);
