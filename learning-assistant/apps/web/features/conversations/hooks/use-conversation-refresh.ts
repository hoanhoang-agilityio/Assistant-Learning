import { useEffect, useRef } from "react";

import { useConversationActions } from "@/features/conversations/hooks/use-conversation-store";
import { fetchConversations } from "@/features/conversations/services/conversations-client";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Reloads the conversation list when a run ends, so titles, stages and
 * scores the run changed show in the sidebar. The old list stays on screen
 * until the new one arrives.
 */
export const useConversationRefresh = () => {
  const { isRunning } = useLearningAgent();
  const { setConversations } = useConversationActions();
  const wasRunningRef = useRef(isRunning);

  useEffect(() => {
    const hasFinished = wasRunningRef.current && !isRunning;
    wasRunningRef.current = isRunning;
    if (!hasFinished) {
      return;
    }

    fetchConversations().then(setConversations, (error: unknown) => {
      console.error("[conversations] Refreshing failed", error);
    });
  }, [isRunning, setConversations]);
};
