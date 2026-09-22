import { useAgent, UseAgentUpdate } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { useCallback, useSyncExternalStore } from "react";

import { readLearningState } from "@/utils/learning-state";

const UPDATES = [
  UseAgentUpdate.OnStateChanged,
  UseAgentUpdate.OnRunStatusChanged,
];

/**
 * The learning agent and its validated state. Re-renders on state and run
 * status changes only, not on every streamed message.
 *
 * The state is also read through `useSyncExternalStore`, which checks for a
 * change between render and subscribe. A component that mounts mid-run (a
 * tool card in the chat) otherwise misses a `STATE_DELTA` that lands in that
 * gap and shows stale state until something else re-renders it.
 */
export const useLearningAgent = () => {
  const { agent } = useAgent({ agentId: LEARNING_AGENT_ID, updates: UPDATES });

  const subscribe = useCallback(
    (onChange: () => void) =>
      agent.subscribe({ onStateChanged: onChange }).unsubscribe,
    [agent],
  );
  const getState = () => agent.state;
  const rawState: unknown = useSyncExternalStore(subscribe, getState, getState);

  return {
    agent,
    state: readLearningState(rawState),
    isRunning: agent.isRunning,
  };
};
