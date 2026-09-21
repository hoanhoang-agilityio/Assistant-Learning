"use client";

import { ChatPanelView } from "@/features/chat/components/ChatPanelView";
import { useChatLayout } from "@/features/chat/hooks/use-chat-layout";

/** The chat panel, sized and shown from the saved layout. */
export const ChatPanel = () => {
  const { chatWidth, isChatOpen, handleToggleChat } = useChatLayout();

  return (
    <ChatPanelView
      width={chatWidth}
      isOpen={isChatOpen}
      onCollapse={handleToggleChat}
    />
  );
};
