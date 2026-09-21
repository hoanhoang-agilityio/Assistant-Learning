import { MessageSquare, PanelLeftOpen } from "lucide-react";

import { CHAT_PANEL_ID } from "@/constants/layout";

export interface ChatRailViewProps {
  onOpen: () => void;
}

/** Slim bar shown in place of the collapsed chat, with a button to reopen it. */
export const ChatRailView = ({ onOpen }: ChatRailViewProps) => (
  <div className="flex w-12 shrink-0 flex-col items-center gap-3 border-r border-slate-200 bg-white py-3 dark:border-slate-800 dark:bg-slate-900/80">
    <button
      type="button"
      onClick={onOpen}
      aria-label="Open chat"
      aria-controls={CHAT_PANEL_ID}
      aria-expanded={false}
      title="Open chat"
      className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-indigo-50 hover:text-indigo-600 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-indigo-300"
    >
      <PanelLeftOpen className="h-4 w-4" />
    </button>
    <MessageSquare aria-hidden className="h-4 w-4 text-indigo-500" />
  </div>
);
