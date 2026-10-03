"use client";

import { CopilotChatConfigurationProvider } from "@copilotkit/react-core/v2";
import type { ReactNode } from "react";

import { useActiveConversation } from "@/features/conversations/hooks/use-conversation-store";

export interface ConversationThreadProps {
  /**
   * Whether the chat inside may connect to the thread. Only one chat should:
   * each one that does replays the whole thread from the checkpoint.
   */
  canConnect?: boolean;
  children: ReactNode;
}

/**
 * Points the chat inside it at the open conversation's thread. A started
 * conversation is an explicit thread: the chat reconnects to it, and the
 * server rebuilds its messages, canvas and Board from the checkpoint. A new
 * one is not, so the chat shows its welcome screen and connects to nothing.
 * A chat that may not connect gets the same thread, never as explicit, and
 * shows what the connecting chat loads into the shared agent. The flag
 * cannot be turned off below a provider that sets it, so each chat has its
 * own provider and none wraps both.
 */
export const ConversationThread = ({
  canConnect = true,
  children,
}: ConversationThreadProps) => {
  const active = useActiveConversation();

  if (!active) {
    return null;
  }

  return (
    <CopilotChatConfigurationProvider
      threadId={active.id}
      hasExplicitThreadId={canConnect && !active.isNew}
    >
      {children}
    </CopilotChatConfigurationProvider>
  );
};
