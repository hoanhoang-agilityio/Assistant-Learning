import {
  type BaseEvent,
  type CustomEvent,
  EventType,
  type StateDeltaEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import {
  DELETE_BOARD_SURFACE_TOOL,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import type { Draft, LearningState, SubagentTool } from "@repo/shared/schemas";
import { concatMap, type OperatorFunction } from "rxjs";

import { DRAFT_EVENTS } from "../constants/agents";
import type { BoardDraftEvent, StateUpdate } from "../types/agents";
import {
  applyBoardDraft,
  applyDraft,
  applyRemovalResult,
  applySurfaceResult,
  applyToolResult,
  createStartUpdate,
  interruptTask,
  isSubagentTool,
  needsTopicConfirmation,
} from "./state-deltas";

/**
 * Keeps the client's state in step with subagent tools. Emits a `STATE_DELTA`
 * after a subagent's `TOOL_CALL_START` (status running) and after its
 * `TOOL_CALL_RESULT` (result, stage and status), and clears a task left
 * running before the run finishes or fails. A `research` call that must wait
 * for the student to confirm a new topic changes nothing, so the canvas does
 * not move. A `renderSurface` result for the canvas, or an
 * `updateBoardSurface` result, writes its view to the Board;
 * a `deleteBoardSurface` result takes its views off. The internal draft
 * events (`DRAFT_EVENTS`) become `state.draft` and `state.boardDraft`, so the
 * canvas shows output as it streams; they are not forwarded. `onStateChange`
 * receives each new state, so later tools in the same run see earlier
 * results.
 */
export const syncStateFromTools = (
  initial: LearningState,
  onStateChange?: (state: LearningState) => void,
): OperatorFunction<BaseEvent, BaseEvent> => {
  let state = initial;
  const runningTools = new Map<string, SubagentTool>();
  const surfaceCalls = new Set<string>();
  const removalCalls = new Set<string>();

  const toDeltaEvents = (update: StateUpdate): StateDeltaEvent[] => {
    state = update.state;
    onStateChange?.(state);
    return update.patch.length > 0
      ? [{ type: EventType.STATE_DELTA, delta: update.patch }]
      : [];
  };

  const toDraftDeltaEvents = ({ name, value }: CustomEvent): BaseEvent[] => {
    const update =
      name === DRAFT_EVENTS.stage
        ? applyDraft(state, value as Draft)
        : applyBoardDraft(state, value as BoardDraftEvent);
    return update ? toDeltaEvents(update) : [];
  };
  const draftEventNames: readonly string[] = Object.values(DRAFT_EVENTS);

  return concatMap((event): BaseEvent[] => {
    switch (event.type) {
      case EventType.CUSTOM: {
        const custom = event as CustomEvent;
        return draftEventNames.includes(custom.name)
          ? toDraftDeltaEvents(custom)
          : [event];
      }
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (
          toolCallName === RENDER_SURFACE_TOOL ||
          toolCallName === UPDATE_BOARD_SURFACE_TOOL
        ) {
          surfaceCalls.add(toolCallId);
          return [event];
        }
        if (toolCallName === DELETE_BOARD_SURFACE_TOOL) {
          removalCalls.add(toolCallId);
          return [event];
        }
        if (
          !isSubagentTool(toolCallName) ||
          needsTopicConfirmation(toolCallName, state)
        ) {
          return [event];
        }
        runningTools.set(toolCallId, toolCallName);
        return [
          event,
          ...toDeltaEvents(createStartUpdate(state, toolCallName)),
        ];
      }
      case EventType.TOOL_CALL_RESULT: {
        const { toolCallId, content } = event as ToolCallResultEvent;
        if (surfaceCalls.delete(toolCallId)) {
          const update = applySurfaceResult(state, content);
          return update ? [event, ...toDeltaEvents(update)] : [event];
        }
        if (removalCalls.delete(toolCallId)) {
          const update = applyRemovalResult(state, content);
          return update ? [event, ...toDeltaEvents(update)] : [event];
        }
        const tool = runningTools.get(toolCallId);
        if (!tool) {
          return [event];
        }
        runningTools.delete(toolCallId);
        return [event, ...toDeltaEvents(applyToolResult(state, tool, content))];
      }
      case EventType.RUN_FINISHED:
      case EventType.RUN_ERROR: {
        const update = interruptTask(state);
        return update ? [...toDeltaEvents(update), event] : [event];
      }
      default:
        return [event];
    }
  });
};
