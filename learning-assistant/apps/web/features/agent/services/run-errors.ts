import {
  type BaseEvent,
  EventType,
  type RunErrorEvent,
  type TextMessageContentEvent,
  type TextMessageEndEvent,
  type TextMessageStartEvent,
} from "@ag-ui/client";
import { concatMap, type OperatorFunction } from "rxjs";

import { RUN_ERROR_INTRO } from "@/features/agent/constants/errors";

/** The assistant message that explains a failed run in the chat. */
const createErrorMessageEvents = (text: string): BaseEvent[] => {
  const messageId = crypto.randomUUID();
  const start: TextMessageStartEvent = {
    type: EventType.TEXT_MESSAGE_START,
    messageId,
    role: "assistant",
  };
  const content: TextMessageContentEvent = {
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId,
    delta: `${RUN_ERROR_INTRO} ${text}`,
  };
  const end: TextMessageEndEvent = {
    type: EventType.TEXT_MESSAGE_END,
    messageId,
  };
  return [start, content, end];
};

/**
 * A `RUN_ERROR` alone leaves the chat silent. This puts a readable assistant
 * message in front of it, from `formatMessage(error message)`, so the student
 * sees what failed (a bad key, a rate limit…) and what to do. The
 * `RUN_ERROR` still follows, so the client knows the run failed.
 */
export const explainRunErrors = (
  formatMessage: (message: string) => string,
): OperatorFunction<BaseEvent, BaseEvent> =>
  concatMap((event): BaseEvent[] =>
    event.type === EventType.RUN_ERROR
      ? [
          ...createErrorMessageEvents(
            formatMessage((event as RunErrorEvent).message),
          ),
          event,
        ]
      : [event],
  );
