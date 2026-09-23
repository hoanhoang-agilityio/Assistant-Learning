"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";
import { MessageSquare, PanelLeftClose, PictureInPicture2 } from "lucide-react";

import { CHAT_PANEL_ID } from "@/constants/layout";
import {
  CHAT_TITLE,
  CHAT_VIEW_PROPS,
} from "@/features/chat/constants/chat-view";

const HEADER_BUTTON_CLASS =
  "rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200";

export interface ChatPanelViewProps {
  /** Panel width in px. */
  width: number;
  isOpen: boolean;
  onCollapse: () => void;
  /** Moves the chat into a floating popup. */
  onPopOut: () => void;
}

/**
 * Left panel: the Supervisor chat, restyled to match the reference UI. It
 * stays mounted while hidden so the draft and scroll position survive.
 */
export const ChatPanelView = ({
  width,
  isOpen,
  onCollapse,
  onPopOut,
}: ChatPanelViewProps) => (
  <aside
    id={CHAT_PANEL_ID}
    style={{ width }}
    className={`${isOpen ? "flex" : "hidden"} shrink-0 flex-col bg-white dark:bg-slate-900/80`}
  >
    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/50 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/30">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-indigo-500" />
        <span className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-slate-400">
          {CHAT_TITLE}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          Online
        </span>
        <button
          type="button"
          onClick={onPopOut}
          aria-label="Pop out chat"
          title="Pop out chat"
          className={HEADER_BUTTON_CLASS}
        >
          <PictureInPicture2 className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onCollapse}
          aria-label="Collapse chat"
          aria-controls={CHAT_PANEL_ID}
          aria-expanded={isOpen}
          title="Collapse chat"
          className={HEADER_BUTTON_CLASS}
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>
    </div>

    <CopilotChat {...CHAT_VIEW_PROPS} className="min-h-0 flex-1" />
  </aside>
);
