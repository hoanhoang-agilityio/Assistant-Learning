import {
  type BaseEvent,
  type CustomEvent,
  EventType,
  type ToolCallArgsEvent,
  type ToolCallEndEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import {
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import type { Draft } from "@repo/shared/schemas";
import { parsePartialJson } from "ai";
import {
  concatMap,
  from,
  type Observable,
  of,
  type OperatorFunction,
} from "rxjs";

import {
  DRAFT_EVENTS,
  DRAFT_INTERVAL_MS,
} from "@/features/agent/constants/agents";
import type { BoardDraftEvent } from "@/features/agent/types/agents";

/** The internal event that carries a subagent's draft to `syncStateFromTools`. */
export const toStageDraftEvent = (draft: Draft): CustomEvent => ({
  type: EventType.CUSTOM,
  name: DRAFT_EVENTS.stage,
  value: draft,
});

/**
 * Calls `fn` at most once per `intervalMs`, dropping the calls in between.
 * Each draft holds everything so far, so a dropped one loses nothing the
 * next one (or the result) does not bring.
 */
export const throttleDrafts = <T>(
  fn: (value: T) => void,
  now: () => number = Date.now,
): ((value: T) => void) => {
  let sentAt = -Infinity;
  return (value) => {
    const time = now();
    if (time - sentAt >= DRAFT_INTERVAL_MS) {
      sentAt = time;
      fn(value);
    }
  };
};

interface SurfaceCall {
  toolCallName: string;
  /** The arguments' JSON so far. */
  text: string;
  sentAt: number;
}

const SURFACE_TOOLS: readonly string[] = [
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
];

/**
 * Streams the Board: while the Supervisor writes a `renderSurface` or
 * `updateBoardSurface` call, its arguments so far are parsed (partial JSON)
 * and follow the `TOOL_CALL_ARGS` event as an internal board-draft event, at
 * most once per `DRAFT_INTERVAL_MS`. `syncStateFromTools` decides what can
 * be drawn. Every event passes through, in order.
 */
export const streamBoardDrafts = (
  now: () => number = Date.now,
): OperatorFunction<BaseEvent, BaseEvent> => {
  const calls = new Map<string, SurfaceCall>();

  const withDraft = async (
    event: BaseEvent,
    toolCallId: string,
    { toolCallName, text }: SurfaceCall,
  ): Promise<BaseEvent[]> => {
    const { value } = await parsePartialJson(text);
    if (value === undefined) {
      return [event];
    }
    const draft: BoardDraftEvent = { toolCallId, toolCallName, args: value };
    return [
      event,
      { type: EventType.CUSTOM, name: DRAFT_EVENTS.board, value: draft },
    ];
  };

  return concatMap((event): Observable<BaseEvent> => {
    switch (event.type) {
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (SURFACE_TOOLS.includes(toolCallName)) {
          calls.set(toolCallId, { toolCallName, text: "", sentAt: -Infinity });
        }
        return of(event);
      }
      case EventType.TOOL_CALL_ARGS: {
        const { toolCallId, delta } = event as ToolCallArgsEvent;
        const call = calls.get(toolCallId);
        if (!call) {
          return of(event);
        }
        call.text += delta;
        const time = now();
        if (time - call.sentAt < DRAFT_INTERVAL_MS) {
          return of(event);
        }
        call.sentAt = time;
        return from(withDraft(event, toolCallId, call)).pipe(
          concatMap((events) => events),
        );
      }
      case EventType.TOOL_CALL_END: {
        const { toolCallId } = event as ToolCallEndEvent;
        calls.delete(toolCallId);
        return of(event);
      }
      default:
        return of(event);
    }
  });
};
