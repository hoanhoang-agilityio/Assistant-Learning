"use client";

import { ChatRailView } from "@/features/chat/components/ChatRailView";
import { useChatLayout } from "@/features/chat/hooks/use-chat-layout";

/** Shows the rail only while the chat is collapsed. */
export const ChatRail = () => {
  const { isChatOpen, handleToggleChat } = useChatLayout();
  if (isChatOpen) {
    return null;
  }

  return <ChatRailView onOpen={handleToggleChat} />;
};
