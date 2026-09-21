"use client";

import { BotAvatar } from "@/features/chat/components/BotAvatar";
import { ASSISTANT_BUBBLE_CLASS } from "@/features/chat/constants/chat";
import type { AssistantMessageLayout } from "@/features/chat/types/chat";

/**
 * Assistant turn: avatar, a bubble for text, then tool progress cards. Passed
 * as the slot's `children` so CopilotKit keeps its own message wiring.
 */
export const renderAssistantMessage: AssistantMessageLayout = ({
  markdownRenderer,
  toolCallsView,
  toolbar,
  message,
  toolbarVisible,
}) => {
  const hasContent = Boolean(message.content?.trim());
  return (
    <div className="flex justify-start gap-3 pt-4" data-message-id={message.id}>
      <BotAvatar />
      <div className="flex max-w-[82%] min-w-0 flex-col gap-2">
        {hasContent && (
          <div className={`${ASSISTANT_BUBBLE_CLASS} chat-markdown`}>
            {markdownRenderer}
          </div>
        )}
        {toolCallsView}
        {hasContent && toolbarVisible && toolbar}
      </div>
    </div>
  );
};
