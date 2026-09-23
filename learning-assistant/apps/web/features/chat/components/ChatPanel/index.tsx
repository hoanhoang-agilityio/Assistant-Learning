"use client";

import { ChatPanelView } from "@/features/chat/components/ChatPanelView";
import { useChatLayout } from "@/features/chat/hooks/use-chat-layout";

/** The docked chat panel, sized and shown from the saved layout. */
export const ChatPanel = () => {
  const { chatWidth, isDocked, handleHide, handlePopOut } = useChatLayout();

  return (
    <ChatPanelView
      width={chatWidth}
      isOpen={isDocked}
      onCollapse={handleHide}
      onPopOut={handlePopOut}
    />
  );
};
