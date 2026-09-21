"use client";

import { UserAvatar } from "@/features/chat/components/UserAvatar";
import type { UserMessageLayout } from "@/features/chat/types/chat";
import { getMessageText } from "@/features/chat/utils/messages";

/** User turn: a right-aligned indigo bubble with the user's avatar. */
export const renderUserMessage: UserMessageLayout = ({ message }) => (
  <div className="flex justify-end gap-3 pt-4" data-message-id={message.id}>
    <div className="max-w-[82%] rounded-2xl rounded-br-none bg-indigo-600 px-4 py-2.5 text-xs leading-relaxed whitespace-pre-wrap text-white shadow-sm">
      {getMessageText(message.content)}
    </div>
    <UserAvatar />
  </div>
);
