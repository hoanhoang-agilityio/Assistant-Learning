import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import { useCopilotKit } from "@copilotkit/react-core/v2";

import { A2UI_ACTION_PROP } from "@/features/canvas/constants/a2ui";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Starts a run that carries a quiz Submit in `forwardedProps`; the agent
 * grades it in code, without the LLM deciding.
 */
export const useSubmitQuiz = () => {
  const { copilotkit } = useCopilotKit();
  const { agent } = useLearningAgent();

  return (message: A2UIClientEventMessage) => {
    copilotkit
      .runAgent({ agent, forwardedProps: { [A2UI_ACTION_PROP]: message } })
      .catch((error: unknown) => {
        console.error("[quiz] Submitting the quiz failed", error);
      });
  };
};
