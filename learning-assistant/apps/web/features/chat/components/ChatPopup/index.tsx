"use client";

import { ChatPopupView } from "@/features/chat/components/ChatPopupView";
import { useChatPopup } from "@/features/chat/hooks/use-chat-popup";

/** The popup chat, shown, open and sized from the layout. */
export const ChatPopup = () => {
  const { isVisible, isOpen, width, handleOpenChange } = useChatPopup();

  return (
    <ChatPopupView
      isVisible={isVisible}
      isOpen={isOpen}
      width={width}
      onOpenChange={handleOpenChange}
    />
  );
};
