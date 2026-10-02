import { useEffect, useState } from "react";

import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";
import {
  useActiveConversation,
  useConversationActions,
  useConversations,
  useConversationStore,
} from "@/features/conversations/hooks/use-conversation-store";
import {
  createConversation,
  fetchConversations,
} from "@/features/conversations/services/conversations-client";
import {
  pickConversation,
  toActiveConversation,
} from "@/features/conversations/utils/conversations";
import { useRetakeRequestStore } from "@/hooks/use-retake-request-store";

/**
 * Loads the user's conversations once the stores are hydrated and opens
 * one: the one a Retake link names, else the conversation open last time,
 * else the most recent, else a new one. The chat waits for this, so its first run always has a conversation
 * the server knows.
 */
export const useConversationBootstrap = (isHydrated: boolean) => {
  const conversations = useConversations();
  const active = useActiveConversation();
  const { setConversations, openConversation } = useConversationActions();
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }

    let isCancelled = false;
    const load = async () => {
      const loaded = await fetchConversations();
      const { conversationId: retakeId, actions } =
        useRetakeRequestStore.getState();
      const isRetakeKnown = loaded.some(({ id }) => id === retakeId);
      if (!isRetakeKnown) {
        actions.clearRetake();
      }
      const savedId = isRetakeKnown
        ? (retakeId ?? undefined)
        : useConversationStore.getState().active?.id;
      const picked =
        pickConversation(loaded, savedId) ?? (await createConversation());
      if (isCancelled) {
        return;
      }
      setConversations(
        loaded.some(({ id }) => id === picked.id)
          ? loaded
          : [picked, ...loaded],
      );
      openConversation(toActiveConversation(picked));
    };
    load().catch((loadError: unknown) => {
      console.error("[conversations] Loading failed", loadError);
      if (!isCancelled) {
        setError(CONVERSATION_COPY.loadFailed);
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [isHydrated, attempt, setConversations, openConversation]);

  const handleRetry = () => {
    setError(null);
    setAttempt((count) => count + 1);
  };

  return {
    isReady: error === null && conversations !== null && active !== null,
    error,
    handleRetry,
  };
};
