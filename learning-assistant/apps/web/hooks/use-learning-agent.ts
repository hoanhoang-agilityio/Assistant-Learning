import { useAgent, UseAgentUpdate } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { readLearningState } from "@/utils/learning-state";

const UPDATES = [
  UseAgentUpdate.OnStateChanged,
  UseAgentUpdate.OnRunStatusChanged,
];

/**
 * The learning agent and its validated state. Re-renders on state and run
 * status changes only, not on every streamed message.
 */
export const useLearningAgent = () => {
  const { agent } = useAgent({ agentId: LEARNING_AGENT_ID, updates: UPDATES });

  return {
    agent,
    state: readLearningState(agent.state),
    isRunning: agent.isRunning,
  };
};
