"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { MessageSquare, PanelLeftClose } from "lucide-react";

import { CHAT_PANEL_ID } from "@/constants/layout";
import { renderAssistantMessage } from "@/features/chat/components/AssistantMessage";
import { ChatWelcome } from "@/features/chat/components/ChatWelcome";
import { TypingCursor } from "@/features/chat/components/TypingCursor";
import { renderUserMessage } from "@/features/chat/components/UserMessage";
import { WELCOME_TEXT } from "@/features/chat/constants/chat";

const SUGGESTION_PILL_CLASS =
  "shrink-0 rounded-full border border-slate-200 px-2.5 py-1 text-[11px] whitespace-nowrap text-slate-600 transition-all hover:border-indigo-200 hover:bg-indigo-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800";

export interface ChatPanelViewProps {
  /** Panel width in px. */
  width: number;
  isOpen: boolean;
  onCollapse: () => void;
}

/**
 * Left panel: the Supervisor chat, restyled to match the reference UI. It
 * stays mounted while collapsed so the draft and scroll position survive.
 */
export const ChatPanelView = ({
  width,
  isOpen,
  onCollapse,
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
          Assistant Chat
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          Online
        </span>
        <button
          type="button"
          onClick={onCollapse}
          aria-label="Collapse chat"
          aria-controls={CHAT_PANEL_ID}
          aria-expanded={isOpen}
          title="Collapse chat"
          className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>
    </div>

    <CopilotChat
      agentId={LEARNING_AGENT_ID}
      className="min-h-0 flex-1"
      labels={{
        chatInputPlaceholder: "Ask your AI tutor anything...",
        welcomeMessageText: WELCOME_TEXT,
      }}
      welcomeScreen={ChatWelcome}
      messageView={{
        className: "px-4 pb-4",
        assistantMessage: { children: renderAssistantMessage },
        userMessage: { children: renderUserMessage },
        cursor: TypingCursor,
      }}
      suggestionView={{
        className:
          "suggestion-scroll flex flex-nowrap items-center gap-1.5 overflow-x-auto border-t border-slate-100 px-4 py-2 dark:border-slate-800/80",
        suggestion: { className: SUGGESTION_PILL_CLASS },
      }}
      input={{
        className: "border-t border-slate-200 p-3 dark:border-slate-800",
      }}
    />
  </aside>
);
