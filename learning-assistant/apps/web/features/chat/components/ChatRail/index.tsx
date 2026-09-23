"use client";

import { ChatRailView } from "@/features/chat/components/ChatRailView";
import { useChatLayout } from "@/features/chat/hooks/use-chat-layout";

/** The slim bar shown while the chat is hidden. */
export const ChatRail = () => {
  const { handleOpen } = useChatLayout();

  return <ChatRailView onOpen={handleOpen} />;
};
