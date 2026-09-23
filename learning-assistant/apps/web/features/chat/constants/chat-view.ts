import type { CopilotChatProps } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { renderAssistantMessage } from "@/features/chat/components/AssistantMessage";
import { ChatWelcome } from "@/features/chat/components/ChatWelcome";
import { TypingCursor } from "@/features/chat/components/TypingCursor";
import { renderUserMessage } from "@/features/chat/components/UserMessage";
import { WELCOME_TEXT } from "@/features/chat/constants/chat";

const SUGGESTION_PILL_CLASS =
  "shrink-0 rounded-full border border-slate-200 px-2.5 py-1 text-[11px] whitespace-nowrap text-slate-600 transition-all hover:border-indigo-200 hover:bg-indigo-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800";

export const CHAT_TITLE = "Assistant Chat";

/**
 * The chat's look, shared by the docked panel and the popup so both show the
 * same messages, cards and suggestions.
 */
export const CHAT_VIEW_PROPS: Pick<
  CopilotChatProps,
  | "agentId"
  | "labels"
  | "welcomeScreen"
  | "messageView"
  | "suggestionView"
  | "input"
> = {
  agentId: LEARNING_AGENT_ID,
  labels: {
    chatInputPlaceholder: "Ask your AI tutor anything...",
    welcomeMessageText: WELCOME_TEXT,
    modalHeaderTitle: CHAT_TITLE,
  },
  welcomeScreen: ChatWelcome,
  messageView: {
    className: "px-4 pb-4",
    assistantMessage: { children: renderAssistantMessage },
    userMessage: { children: renderUserMessage },
    cursor: TypingCursor,
  },
  suggestionView: {
    className:
      "suggestion-scroll flex flex-nowrap items-center gap-1.5 overflow-x-auto border-t border-slate-100 px-4 py-2 dark:border-slate-800/80",
    suggestion: { className: SUGGESTION_PILL_CLASS },
  },
  input: {
    className: "border-t border-slate-200 p-3 dark:border-slate-800",
  },
};
