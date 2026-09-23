"use client";

import { ChatPopupView } from "@/features/chat/components/ChatPopupView";
import { useChatPopup } from "@/features/chat/hooks/use-chat-popup";

/** The popup chat, open state and width from the layout. */
export const ChatPopup = () => {
  const { isOpen, width, handleOpenChange } = useChatPopup();

  return (
    <ChatPopupView
      isOpen={isOpen}
      width={width}
      onOpenChange={handleOpenChange}
    />
  );
};
