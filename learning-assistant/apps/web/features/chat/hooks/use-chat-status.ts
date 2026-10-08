import { useCopilotKit } from "@copilotkit/react-core/v2";
import { useCallback, useSyncExternalStore } from "react";

import type { RuntimeConnection } from "@/features/chat/types/chat";
import { getChatStatus } from "@/features/chat/utils/chat-status";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * The chat header's status: starting until the runtime connects, then online
 * or thinking while the agent runs, and offline if the connection fails.
 */
export const useChatStatus = () => {
  const { copilotkit } = useCopilotKit();
  const { isRunning } = useLearningAgent();

  const subscribe = useCallback(
    (onChange: () => void) =>
      copilotkit.subscribe({ onRuntimeConnectionStatusChanged: onChange })
        .unsubscribe,
    [copilotkit],
  );
  const getConnection = (): RuntimeConnection =>
    copilotkit.runtimeConnectionStatus;
  const connection = useSyncExternalStore(
    subscribe,
    getConnection,
    getConnection,
  );

  return getChatStatus(connection, isRunning);
};
