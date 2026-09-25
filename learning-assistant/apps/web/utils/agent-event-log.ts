import { type AGUIEvent, type BaseEvent, EventType } from "@ag-ui/client";

import {
  AGENT_EVENT_LOG_MAX_TEXT,
  AGENT_EVENT_LOG_PREFIX,
} from "@/constants/agent-event-log";

const truncate = (text: string) =>
  text.length > AGENT_EVENT_LOG_MAX_TEXT
    ? `${text.slice(0, AGENT_EVENT_LOG_MAX_TEXT)}…`
    : text;

/** The one detail worth seeing at a glance for an event, or `""`. */
export const describeAgentEvent = (baseEvent: BaseEvent): string => {
  // Every event on the wire is one of the union's members.
  const event = baseEvent as AGUIEvent;

  switch (event.type) {
    case EventType.TEXT_MESSAGE_START:
      return event.role ?? "";
    case EventType.TOOL_CALL_START:
      return event.toolCallName;
    case EventType.TOOL_CALL_RESULT:
      return truncate(event.content);
    case EventType.STATE_SNAPSHOT:
      return Object.keys(event.snapshot ?? {}).join(", ");
    case EventType.STATE_DELTA:
      return event.delta
        .map(
          (operation: { op: string; path: string }) =>
            `${operation.op} ${operation.path}`,
        )
        .join(", ");
    case EventType.ACTIVITY_SNAPSHOT:
      return `${event.activityType} ${event.messageId}`;
    case EventType.CUSTOM:
      return event.name;
    case EventType.STEP_STARTED:
    case EventType.STEP_FINISHED:
      return event.stepName;
    case EventType.RUN_ERROR:
      return truncate(event.message);
    default:
      return "";
  }
};

/** Milliseconds since the run started, as `+123ms`. */
export const formatElapsed = (elapsedMs: number) =>
  `+${Math.round(elapsedMs)}ms`;

/**
 * One line of the agent event log: prefix, time since the run started, event
 * type, its detail, and how many streamed deltas arrived since the last line.
 */
export const formatEventLine = (
  event: BaseEvent,
  elapsedMs: number,
  streamedCount = 0,
) => {
  const detail = describeAgentEvent(event);
  const streamed = streamedCount > 0 ? `(${streamedCount} streamed)` : "";

  return [
    AGENT_EVENT_LOG_PREFIX,
    formatElapsed(elapsedMs),
    event.type,
    detail,
    streamed,
  ]
    .filter(Boolean)
    .join(" ");
};
