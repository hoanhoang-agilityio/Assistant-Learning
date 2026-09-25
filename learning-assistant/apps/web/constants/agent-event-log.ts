import { EventType } from "@ag-ui/client";

/** Prefix on every agent event log line, to filter the console by. */
export const AGENT_EVENT_LOG_PREFIX = "[ag-ui]";

/** Longest tool result or error text a log line shows before cutting it. */
export const AGENT_EVENT_LOG_MAX_TEXT = 80;

/**
 * Events that arrive once per streamed token. The log counts them and shows
 * the count on the next line instead of printing each one.
 */
export const STREAMED_EVENT_TYPES: ReadonlySet<string> = new Set([
  EventType.TEXT_MESSAGE_CONTENT,
  EventType.TEXT_MESSAGE_CHUNK,
  EventType.TOOL_CALL_ARGS,
  EventType.TOOL_CALL_CHUNK,
  EventType.REASONING_MESSAGE_CONTENT,
]);
