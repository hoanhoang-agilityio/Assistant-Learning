import {
  type BaseEvent,
  EventType,
  type StateDeltaEvent,
  type StateSnapshotEvent,
  type ToolCallArgsEvent,
  type ToolCallEndEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import { parsePartialJson } from "@langchain/core/output_parsers";
import {
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import type { BoardDraft, BoardSurface } from "@repo/shared/schemas";
import { compare, type Operation } from "fast-json-patch";
import { concatMap, type OperatorFunction } from "rxjs";

import { DRAFT_INTERVAL_MS } from "../../constants/agents";
import { toBoardDraft } from "../../utils/board-draft";

const SURFACE_TOOLS: readonly string[] = [
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
];

interface SurfaceCall {
  toolCallName: string;
  /** The arguments' JSON so far. */
  text: string;
  sentAt: number;
}

/** The draft the browser holds, and the Board it was started on. */
interface OpenDraft {
  toolCallId: string;
  draft: BoardDraft;
  board: string;
}

const toDelta = (delta: Operation[]): StateDeltaEvent => ({
  type: EventType.STATE_DELTA,
  delta,
});

const clearDraft = (): StateDeltaEvent =>
  toDelta([{ op: "add", path: "/boardDraft", value: null }]);

/**
 * The delta that turns the browser's draft into `draft`: the whole draft for
 * a new one, the diff inside it while the same one grows.
 */
const toDraftDelta = (
  previous: BoardDraft | null,
  draft: BoardDraft,
): StateDeltaEvent =>
  toDelta(
    previous?.id === draft.id
      ? compare(previous, draft).map((operation) => ({
          ...operation,
          path: `/boardDraft${operation.path}`,
        }))
      : [{ op: "add", path: "/boardDraft", value: draft }],
  );

/**
 * Streams a Board view to the canvas while the Supervisor writes it. The
 * graph never holds a draft: its arguments only exist as `TOOL_CALL_ARGS`.
 * So while a `renderSurface` (canvas) or `updateBoardSurface` call streams,
 * its arguments so far are parsed and sent as a `STATE_DELTA` on
 * `boardDraft`, at most once per `DRAFT_INTERVAL_MS`.
 *
 * The draft stays until the Board changes: snapshots that still hold the
 * Board it started on carry it too, so the step between the model and the
 * tool does not blank it. A call that changes nothing (an invalid tree)
 * clears it with its result, and so does the end of the run.
 */
export const streamBoardDrafts = (
  now: () => number = Date.now,
): OperatorFunction<BaseEvent, BaseEvent> => {
  const calls = new Map<string, SurfaceCall>();
  let board: BoardSurface[] = [];
  let open: OpenDraft | null = null;

  const onSnapshot = (event: StateSnapshotEvent): BaseEvent => {
    const snapshot = event.snapshot as { board?: BoardSurface[] };
    board = snapshot.board ?? board;
    if (!open) {
      return event;
    }
    if (JSON.stringify(board) !== open.board) {
      open = null;
      return event;
    }
    return { ...event, snapshot: { ...snapshot, boardDraft: open.draft } };
  };

  const onArgs = (event: ToolCallArgsEvent): BaseEvent[] => {
    const { toolCallId, delta } = event;
    const call = calls.get(toolCallId);
    if (!call) {
      return [event];
    }
    call.text += delta;
    const time = now();
    if (time - call.sentAt < DRAFT_INTERVAL_MS) {
      return [event];
    }
    const draft = toBoardDraft(board, {
      toolCallId,
      toolCallName: call.toolCallName,
      args: parsePartialJson(call.text),
    });
    if (!draft) {
      return [event];
    }
    call.sentAt = time;
    const previous = open?.toolCallId === toolCallId ? open : null;
    open = {
      toolCallId,
      draft,
      board: previous?.board ?? JSON.stringify(board),
    };
    return [event, toDraftDelta(previous?.draft ?? null, draft)];
  };

  return concatMap((event): BaseEvent[] => {
    switch (event.type) {
      case EventType.STATE_SNAPSHOT:
        return [onSnapshot(event as StateSnapshotEvent)];
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (SURFACE_TOOLS.includes(toolCallName)) {
          calls.set(toolCallId, { toolCallName, text: "", sentAt: -Infinity });
        }
        return [event];
      }
      case EventType.TOOL_CALL_ARGS:
        return onArgs(event as ToolCallArgsEvent);
      case EventType.TOOL_CALL_END:
        calls.delete((event as ToolCallEndEvent).toolCallId);
        return [event];
      case EventType.TOOL_CALL_RESULT: {
        const { toolCallId } = event as ToolCallResultEvent;
        if (open?.toolCallId !== toolCallId) {
          return [event];
        }
        open = null;
        return [event, clearDraft()];
      }
      case EventType.RUN_FINISHED:
      case EventType.RUN_ERROR: {
        if (!open) {
          return [event];
        }
        open = null;
        return [clearDraft(), event];
      }
      default:
        return [event];
    }
  });
};
