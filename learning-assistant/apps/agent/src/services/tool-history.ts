import {
  type BaseEvent,
  EventType,
  type Message,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import { concatMap, type OperatorFunction } from "rxjs";

import { LOST_TOOL_RESULT } from "../constants/errors";
import { TOOL_ERRORS } from "../constants/tools";

/**
 * What a lost tool call returns. `{ ok: false, error }` is the shape the
 * subagent tools fail with, so the chat's cards and the state show it as a
 * failure like any other.
 */
const LOST_RESULT_CONTENT = JSON.stringify({
  ok: false,
  error: LOST_TOOL_RESULT,
});

/**
 * What a call cut off by Stop returns: the same error `runSubagent` gives a
 * stopped step, so the state and the chat card show it as stopped.
 */
const STOPPED_RESULT_CONTENT = JSON.stringify({
  ok: false,
  error: TOOL_ERRORS.stopped,
});

/**
 * `BuiltInAgent` emits no `TOOL_CALL_RESULT` when the AI SDK rejects a tool
 * call (invalid arguments, unknown tool name). The model is told within the
 * run, but the client keeps a tool call without a result, and the next
 * request then fails with a missing tool result error. This adds a failure
 * result for each such call before the run ends. Calls to the client's own
 * tools (`clientToolNames`) are left alone: the client answers those. A run
 * aborted by Stop (`signal`) ends with its running call unanswered too; that
 * call gets the stopped result instead of a failure.
 */
export const closeLostToolCalls = (
  clientToolNames: ReadonlySet<string>,
  signal?: AbortSignal,
): OperatorFunction<BaseEvent, BaseEvent> => {
  const open = new Set<string>();

  return concatMap((event): BaseEvent[] => {
    switch (event.type) {
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (!clientToolNames.has(toolCallName)) {
          open.add(toolCallId);
        }
        return [event];
      }
      case EventType.TOOL_CALL_RESULT:
        open.delete((event as ToolCallResultEvent).toolCallId);
        return [event];
      case EventType.RUN_FINISHED:
      case EventType.RUN_ERROR: {
        const content = signal?.aborted
          ? STOPPED_RESULT_CONTENT
          : LOST_RESULT_CONTENT;
        const results: ToolCallResultEvent[] = [...open].map((toolCallId) => ({
          type: EventType.TOOL_CALL_RESULT,
          messageId: crypto.randomUUID(),
          toolCallId,
          content,
        }));
        open.clear();
        return [...results, event];
      }
      default:
        return [event];
    }
  });
};

/**
 * The history with a failure result after every tool call that has none, so
 * a thread that already lost one (before `closeLostToolCalls`, or a
 * confirmation card left unanswered) can carry on. Each result goes right
 * after the assistant message that made the call.
 */
export const repairToolHistory = (messages: Message[]): Message[] => {
  const answered = new Set(
    messages.flatMap((message) =>
      message.role === "tool" ? [message.toolCallId] : [],
    ),
  );

  return messages.flatMap((message): Message[] => {
    if (message.role !== "assistant" || !message.toolCalls) {
      return [message];
    }
    const lost: Message[] = message.toolCalls
      .filter(({ id }) => !answered.has(id))
      .map(({ id }) => ({
        id: `lost-${id}`,
        role: "tool",
        toolCallId: id,
        content: LOST_RESULT_CONTENT,
      }));
    return [message, ...lost];
  });
};
