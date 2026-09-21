import { useCopilotKit } from "@copilotkit/react-core/v2";

import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Sends a user message to the learning agent from the canvas, as if typed in
 * the chat. The provider adds the settings to `forwardedProps`.
 */
export const useSendMessage = () => {
  const { copilotkit } = useCopilotKit();
  const { agent } = useLearningAgent();

  return (content: string) => {
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content });
    copilotkit.runAgent({ agent }).catch((error: unknown) => {
      console.error("[canvas] Sending a message failed", error);
    });
  };
};
