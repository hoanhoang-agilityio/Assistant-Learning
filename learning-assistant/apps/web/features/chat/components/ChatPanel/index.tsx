"use client";

import { ChatPanelView } from "@/features/chat/components/ChatPanelView";
import { useChatLayout } from "@/features/chat/hooks/use-chat-layout";
import { useChatStatus } from "@/features/chat/hooks/use-chat-status";

/** The docked chat panel, sized and shown from the saved layout, with its status. */
export const ChatPanel = () => {
  const { chatWidth, isDocked, handleHide, handlePopOut } = useChatLayout();
  const status = useChatStatus();

  return (
    <ChatPanelView
      width={chatWidth}
      isOpen={isDocked}
      status={status}
      onCollapse={handleHide}
      onPopOut={handlePopOut}
    />
  );
};
