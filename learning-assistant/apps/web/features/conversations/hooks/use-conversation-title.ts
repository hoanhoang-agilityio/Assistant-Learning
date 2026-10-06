import { createAutoTitle } from "@repo/shared/utils/conversations";
import { useEffect, useRef } from "react";

import { useSealedApiKey } from "@/features/api-key/hooks/use-api-key-store";
import { getMessageText } from "@/features/chat/utils/messages";
import {
  useActiveConversation,
  useConversationActions,
  useConversations,
} from "@/features/conversations/hooks/use-conversation-store";
import { summarizeConversationTitle } from "@/features/conversations/services/conversations-client";
import { isNewConversation } from "@/features/conversations/utils/conversations";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Names a new conversation as soon as its first message is sent, without
 * waiting for the run: the message, cut short, shows in the sidebar at
 * once, and the title summarised from it replaces it when it arrives.
 * Each conversation is asked for once.
 */
export const useConversationTitle = () => {
  const { agent, isRunning } = useLearningAgent();
  const active = useActiveConversation();
  const conversations = useConversations();
  const sealedKey = useSealedApiKey();
  const { updateConversation } = useConversationActions();
  const requestedRef = useRef(new Set<string>());

  useEffect(() => {
    const conversation = conversations?.find(({ id }) => id === active?.id);
    if (
      !isRunning ||
      !sealedKey ||
      !conversation ||
      !isNewConversation(conversation) ||
      requestedRef.current.has(conversation.id)
    ) {
      return;
    }

    const firstMessage = agent.messages.find(({ role }) => role === "user");
    const message = getMessageText(firstMessage?.content).trim();
    const autoTitle = createAutoTitle(message);
    if (!autoTitle) {
      return;
    }

    requestedRef.current.add(conversation.id);
    updateConversation({ ...conversation, title: autoTitle });
    summarizeConversationTitle(conversation.id, message, sealedKey).then(
      updateConversation,
      (error: unknown) => {
        console.error("[conversations] Naming the conversation failed", error);
      },
    );
  }, [agent, active, conversations, isRunning, sealedKey, updateConversation]);
};
