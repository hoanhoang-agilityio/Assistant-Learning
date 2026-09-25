import {
  type BaseEvent,
  EventType,
  type Message,
  type TextMessageChunkEvent,
  type TextMessageContentEvent,
  type TextMessageEndEvent,
  type TextMessageStartEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import { concatMap, type OperatorFunction } from "rxjs";

import { CARD_TOOLS } from "@/features/agent/constants/tools";

type TextEvent =
  | TextMessageStartEvent
  | TextMessageContentEvent
  | TextMessageEndEvent
  | TextMessageChunkEvent;

const TEXT_EVENTS: ReadonlySet<string> = new Set([
  EventType.TEXT_MESSAGE_START,
  EventType.TEXT_MESSAGE_CONTENT,
  EventType.TEXT_MESSAGE_END,
  EventType.TEXT_MESSAGE_CHUNK,
]);

/**
 * A tool result is a failure when it is `{ ok: false }` (subagent tools) or
 * carries an `error` (surface tools). Frontend tools return plain text.
 */
const isSuccess = (content: string): boolean => {
  try {
    const result: unknown = JSON.parse(content);
    return !(
      typeof result === "object" &&
      result !== null &&
      ("error" in result || ("ok" in result && result.ok === false))
    );
  } catch {
    return true;
  }
};

/**
 * Whether the history ends with a card tool's successful result. A frontend
 * tool (theme, layout, settings, chat cards, new topic) finishes on the
 * client, so its result starts the next run.
 */
const endsWithCardResult = (messages: Message[]): boolean => {
  const last = messages.at(-1);
  if (last?.role !== "tool") {
    return false;
  }
  const call = messages
    .flatMap((message) =>
      message.role === "assistant" ? (message.toolCalls ?? []) : [],
    )
    .find(({ id }) => id === last.toolCallId);
  return (
    call !== undefined &&
    CARD_TOOLS.has(call.function.name) &&
    isSuccess(last.content)
  );
};

/**
 * Every card tool shows in the chat what it did, so the Supervisor adds no
 * reply after one succeeds. This drops any text message that starts while
 * the latest tool result (in `history` or in this run) is a card tool's
 * success. A failure, or any other tool's result, lets the reply through, so
 * errors are still explained. Tool calls always pass.
 */
export const muteRepliesAfterCards = (
  history: Message[],
): OperatorFunction<BaseEvent, BaseEvent> => {
  let muted = endsWithCardResult(history);
  const cardCalls = new Set<string>();
  const textMessages = new Map<string, boolean>();

  const isMutedText = ({ messageId }: TextEvent): boolean => {
    if (!messageId) {
      return muted;
    }
    if (!textMessages.has(messageId)) {
      textMessages.set(messageId, muted);
    }
    return textMessages.get(messageId) ?? muted;
  };

  return concatMap((event): BaseEvent[] => {
    if (TEXT_EVENTS.has(event.type)) {
      return isMutedText(event as TextEvent) ? [] : [event];
    }
    switch (event.type) {
      case EventType.TOOL_CALL_START: {
        const { toolCallId, toolCallName } = event as ToolCallStartEvent;
        if (CARD_TOOLS.has(toolCallName)) {
          cardCalls.add(toolCallId);
        }
        return [event];
      }
      case EventType.TOOL_CALL_RESULT: {
        const { toolCallId, content } = event as ToolCallResultEvent;
        muted = cardCalls.delete(toolCallId) && isSuccess(content);
        return [event];
      }
      default:
        return [event];
    }
  });
};
