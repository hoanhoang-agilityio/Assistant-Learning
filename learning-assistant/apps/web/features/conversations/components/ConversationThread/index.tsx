"use client";

import { CopilotChatConfigurationProvider } from "@copilotkit/react-core/v2";
import type { ReactNode } from "react";

import { useActiveConversation } from "@/features/conversations/hooks/use-conversation-store";

export interface ConversationThreadProps {
  children: ReactNode;
}

/**
 * Points every chat inside it at the open conversation's thread. A started
 * conversation is an explicit thread: the chat reconnects to it, and the
 * server rebuilds its messages, canvas and Board from the checkpoint. A new
 * one is not, so the chat shows its welcome screen and connects to nothing.
 */
export const ConversationThread = ({ children }: ConversationThreadProps) => {
  const active = useActiveConversation();

  if (!active) {
    return null;
  }

  return (
    <CopilotChatConfigurationProvider
      threadId={active.id}
      hasExplicitThreadId={!active.isNew}
    >
      {children}
    </CopilotChatConfigurationProvider>
  );
};
