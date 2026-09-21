import {
  type BaseEvent,
  EventType,
  type StateDeltaEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import type { LearningState, SubagentTool } from "@repo/shared/schemas";
import { concatMap, type OperatorFunction } from "rxjs";

import type { StateUpdate } from "../../types/agents";
import {
  applyToolResult,
  interruptTask,
  isSubagentTool,
  handleStartTask,
} from "./state-deltas";

/**
 * Keeps the client's state in step with subagent tools. Emits a `STATE_DELTA`
 * after a subagent's `TOOL_CALL_START` (status running) and after its
 * `TOOL_CALL_RESULT` (result, stage and status), and clears a task left
 * running before the run finishes or fails.
 */
export const syncStateFromTools = (
  initial: LearningState,
): OperatorFunction<BaseEvent, BaseEvent> => {
  let state = initial;
  const runningTools = new Map<string, SubagentTool>();

  const handleConvertToDelta = (update: StateUpdate): StateDeltaEvent[] => {
    state = update.state;
    return update.patch.length > 0
      ? [{ type: EventType.STATE_DELTA, delta: update.patch }]
      : [];
  };

  return concatMap((event): BaseEvent[] => {
    switch (event.type) {
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (!isSubagentTool(toolCallName)) return [event];
        runningTools.set(toolCallId, toolCallName);
        return [
          event,
          ...handleConvertToDelta(handleStartTask(state, toolCallName)),
        ];
      }
      case EventType.TOOL_CALL_RESULT: {
        const { toolCallId, content } = event as ToolCallResultEvent;
        const tool = runningTools.get(toolCallId);
        if (!tool) return [event];
        runningTools.delete(toolCallId);
        return [
          event,
          ...handleConvertToDelta(applyToolResult(state, tool, content)),
        ];
      }
      case EventType.RUN_FINISHED:
      case EventType.RUN_ERROR: {
        const update = interruptTask(state);
        return update ? [...handleConvertToDelta(update), event] : [event];
      }
      default:
        return [event];
    }
  });
};
