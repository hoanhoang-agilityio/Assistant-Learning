import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { CHAT_CARD_LABELS } from "@/features/chat/constants/tools";
import type { ChatCardKind } from "@/features/chat/types/chat";

export interface ChatCardProps {
  kind: ChatCardKind;
  icon: LucideIcon;
  /** Missing while the tool arguments are still streaming. */
  title?: string;
  children?: ReactNode;
}

/** The frame every chat card shares: icon, kind label, title, then its body. */
export const ChatCard = ({
  kind,
  icon: Icon,
  title,
  children,
}: ChatCardProps) => (
  <div className="rounded-xl border border-indigo-200 bg-white px-3 py-2.5 text-xs shadow-sm dark:border-indigo-900/60 dark:bg-slate-800">
    <div className="flex items-center gap-2">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white">
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <span className="block text-[10px] font-medium tracking-wide text-indigo-500 uppercase">
          {CHAT_CARD_LABELS[kind]}
        </span>
        {title ? (
          <span className="block truncate text-sm font-semibold">{title}</span>
        ) : (
          <span className="block h-4 w-24 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        )}
      </div>
    </div>
    {children}
  </div>
);
