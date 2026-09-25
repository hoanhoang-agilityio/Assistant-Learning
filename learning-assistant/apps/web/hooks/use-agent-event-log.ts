import { useAgent, UseAgentUpdate } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { useEffect } from "react";

import {
  AGENT_EVENT_LOG_PREFIX,
  STREAMED_EVENT_TYPES,
} from "@/constants/agent-event-log";
import { IS_DEVELOPMENT } from "@/constants/copilot";
import { formatElapsed, formatEventLine } from "@/utils/agent-event-log";

/** The log reads the agent through a subscription, so it never re-renders. */
const NO_UPDATES: UseAgentUpdate[] = [];

/**
 * Development only: prints each run of the learning agent to the console as a
 * timeline, one line per AG-UI event with the time since the run started.
 * Token deltas are counted, not printed. Each line carries the full event
 * object to expand, and the run's input and final state bracket it. Filter
 * the console by `[ag-ui]` to see only this.
 */
export const useAgentEventLog = () => {
  const { agent } = useAgent({
    agentId: LEARNING_AGENT_ID,
    updates: NO_UPDATES,
  });

  useEffect(() => {
    if (!IS_DEVELOPMENT) {
      return;
    }

    let startedAt = 0;
    let streamedCount = 0;
    const getElapsed = () => performance.now() - startedAt;

    const { unsubscribe } = agent.subscribe({
      onRunInitialized: ({ input }) => {
        startedAt = performance.now();
        streamedCount = 0;
        console.log(`${AGENT_EVENT_LOG_PREFIX} ▶ run ${input.runId}`, input);
      },
      onEvent: ({ event }) => {
        if (STREAMED_EVENT_TYPES.has(event.type)) {
          streamedCount += 1;
          return;
        }

        console.log(formatEventLine(event, getElapsed(), streamedCount), event);
        streamedCount = 0;
      },
      onRunFailed: ({ error }) => {
        console.error(`${AGENT_EVENT_LOG_PREFIX} run failed`, error);
      },
      onRunFinalized: ({ state, messages }) => {
        console.log(
          `${AGENT_EVENT_LOG_PREFIX} ■ run ended ${formatElapsed(getElapsed())}`,
          { state, messages },
        );
      },
    });

    return unsubscribe;
  }, [agent]);
};
